"""Job manager async en proceso (D-031, Fase 1).

Cada generación (cast/keyframes/render/export) corre como una tarea asyncio con
un id; su progreso (líneas de log del pipeline, D-027) se acumula en un buffer y
se transmite en vivo por SSE. Sin broker: single-user local.

`Job` y las transiciones de estado son lógica pura (core testeable); el `run`/
`stream` async se valida con smoke.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable

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
    """Registro de jobs en memoria + ejecución async con captura de logs."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        # T2.6.23: un Event POR CONSUMIDOR del stream. Con uno compartido, dos
        # SSE del mismo job se robaban el despertar (clear ajeno -> cuelgue).
        self._watchers: dict[str, list[asyncio.Event]] = {}

    # --- registro (lógica pura) -------------------------------------------
    def create(self, kind: str, project: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, project=project)
        self._jobs[job.id] = job
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

    def _wake(self, job_id: str) -> None:
        for ev in self._watchers.get(job_id, []):
            ev.set()

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
