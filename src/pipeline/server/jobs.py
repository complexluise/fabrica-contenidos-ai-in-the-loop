"""Job manager async en proceso (D-031, Fase 1).

Cada generación (cast/keyframes/render/export) corre como una tarea asyncio con
un id; su progreso (líneas de log del pipeline, D-027) se acumula en un buffer y
se transmite en vivo por SSE. Sin broker: single-user local.

`Job` y las transiciones de estado son lógica pura (core testeable); el `run`/
`stream` async se valida con smoke.

Persistencia (Ciclo 1 — historia en SQLite):
  - `JobManager` acepta un `db_path` opcional (por defecto LEDGER_PATH de
    telemetry.py). En __init__ crea el `JobStore` y barre los jobs
    queued/running de procesos anteriores (barrido al boot, critico: sin esto
    el guard 409 / `find_active` bloquearia para siempre re-disparar ese
    kind+proyecto).
  - El dict `_jobs` EN MEMORIA sigue siendo la verdad de lo VIVO (el SSE y
    los watchers dependen de el). SQLite es la verdad durable del historial.
  - Transiciones que persisten: create (queued), set_status (running/done/failed).
  - El log completo NO va en SQLite (puede ser MB). Se guarda el tail al
    terminar via `job_store.set_done` / `set_failed`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable

from ..telemetry import LEDGER_PATH
from .job_store import JobStore

_PKG_LOGGER = "pipeline"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobConflictError(RuntimeError):
    """Ya hay un job VIVO del mismo tipo para el mismo proyecto (Fase 2.6).

    Anti doble-gasto: un segundo render/keyframes/cast identico mientras el
    primero corre pagaria dos veces. El server lo mapea a HTTP 409."""


@dataclass
class Job:
    id: str
    kind: str  # cast | keyframes | render | export
    project: str
    status: JobStatus = JobStatus.QUEUED
    logs: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "project": self.project,
            "status": self.status.value, "result": self.result, "error": self.error,
            "log_lines": len(self.logs),
        }


class _JobLogHandler(logging.Handler):
    """Enruta los logs del pipeline al buffer del job que está corriendo."""

    def __init__(self, manager: "JobManager", job_id: str):
        super().__init__(level=logging.INFO)
        self.manager = manager
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.manager.append_log(self.job_id, record.getMessage())
        except Exception:  # noqa: BLE001 — el logging nunca debe romper el job
            pass


class JobManager:
    """Registro de jobs en memoria + ejecución async con captura de logs.

    La memoria es la verdad de lo VIVO (SSE/watchers). SQLite (JobStore)
    es la verdad durable del historial.
    """

    def __init__(self, db_path: Path = LEDGER_PATH):
        self._jobs: dict[str, Job] = {}
        # T2.6.23: un Event POR CONSUMIDOR del stream. Con uno compartido, dos
        # SSE del mismo job se robaban el despertar (clear ajeno -> cuelgue).
        self._watchers: dict[str, list[asyncio.Event]] = {}

        # Persistencia: abre el store y barre los jobs huerfanos del proceso
        # anterior ANTES de que lleguen requests (barrido al boot critico).
        self._store = JobStore(db_path)
        swept = self._store.sweep_interrupted()
        if swept:
            logging.getLogger(_PKG_LOGGER).info(
                "JobManager boot: %d job(s) interrumpidos marcados como failed: %s",
                len(swept), swept,
            )

    # --- registro (lógica pura) -------------------------------------------
    def create(self, kind: str, project: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, project=project)
        self._jobs[job.id] = job
        # Persistir transicion "queued"
        self._store.insert_job(job.id, kind, project)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    def find_active(self, kind: str, project: str) -> Job | None:
        """El job VIVO (queued/running) de este kind+proyecto, si existe."""
        for job in self._jobs.values():
            if job.kind == kind and job.project == project and not job.done:
                return job
        return None

    def append_log(self, job_id: str, line: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.logs.append(line)
            self._wake(job_id)

    def set_status(self, job_id: str, status: JobStatus, *,
                   result: dict | None = None, error: str | None = None) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = status
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        self._wake(job_id)
        # Persistir la transicion en SQLite
        self._persist_transition(job)

    def _persist_transition(self, job: Job) -> None:
        """Escribe la transicion de estado en el JobStore."""
        if job.status == JobStatus.RUNNING:
            self._store.set_running(job.id)
        elif job.status == JobStatus.DONE:
            self._store.set_done(job.id, job.result, log_tail=job.logs)
        elif job.status == JobStatus.FAILED:
            self._store.set_failed(job.id, job.error or "", log_tail=job.logs)
        # QUEUED ya se persiste en create(); los demas no necesitan re-persistir

    def _wake(self, job_id: str) -> None:
        for ev in self._watchers.get(job_id, []):
            ev.set()

    # --- consulta historica (SQLite) --------------------------------------

    def get_from_store(self, job_id: str) -> dict | None:
        """Busca un job en SQLite (para jobs terminados que ya no estan en memoria)."""
        return self._store.get_job(job_id)

    def list_history(self, limit: int = 50, offset: int = 0,
                     since: float | None = None) -> list[dict]:
        """Jobs terminados del historial SQLite, mas nuevos primero."""
        return self._store.list_history(limit=limit, offset=offset, since=since)

    # --- ejecución (async, smoke) -----------------------------------------
    async def run(self, job: Job, coro: Awaitable) -> None:
        """Ejecuta la corrutina del job capturando los logs del pipeline."""
        self.set_status(job.id, JobStatus.RUNNING)
        handler = _JobLogHandler(self, job.id)
        logging.getLogger(_PKG_LOGGER).addHandler(handler)
        try:
            result = await coro
            self.set_status(job.id, JobStatus.DONE,
                            result=result if isinstance(result, dict) else {"ok": True})
        except Exception as exc:  # noqa: BLE001 — el fallo del job no tumba el server
            logging.getLogger(_PKG_LOGGER).error("job %s (%s) FALLO: %s", job.id, job.kind, exc)
            self.set_status(job.id, JobStatus.FAILED, error=str(exc))
        finally:
            logging.getLogger(_PKG_LOGGER).removeHandler(handler)

    def spawn(self, kind: str, project: str, coro: Awaitable) -> Job:
        """Crea el job y lo lanza en segundo plano; devuelve el job al instante.

        T2.6.6: si ya hay un job vivo del mismo kind+proyecto, NO lanza otro
        (JobConflictError -> 409): el doble clic / F5 no debe pagar dos veces."""
        live = self.find_active(kind, project)
        if live is not None:
            if hasattr(coro, "close"):
                coro.close()  # la corrutina rechazada no debe quedar sin esperar
            raise JobConflictError(
                f"Ya hay un trabajo de '{kind}' corriendo para '{project}' "
                f"(job {live.id}). Mira su registro o espera a que termine.")
        job = self.create(kind, project)
        asyncio.create_task(self.run(job, coro))
        return job

    async def stream(self, job_id: str):
        """Generador de líneas nuevas del job hasta que termina (para SSE)."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        ev = asyncio.Event()
        self._watchers.setdefault(job_id, []).append(ev)
        try:
            sent = 0
            while True:
                while sent < len(job.logs):
                    yield job.logs[sent]
                    sent += 1
                if job.done:
                    yield f"__status__:{job.status.value}"
                    return
                await ev.wait()
                ev.clear()
        finally:
            watchers = self._watchers.get(job_id, [])
            if ev in watchers:
                watchers.remove(ev)
