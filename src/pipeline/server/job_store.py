"""Persistencia de jobs en SQLite (historia + trazabilidad).

Usa la MISMA base `out/telemetry.sqlite` que D-079 (costos), con tablas
nuevas aparte de `scene_runs`: `jobs` (estado actual) + `job_events`
(append-only, una fila por transicion de estado).

Cada instancia de `JobStore` abre su propia conexion (no comparte con
`Telemetry`, que es por run). El constructor crea las tablas idempotente
(CREATE TABLE IF NOT EXISTS) igual que telemetry.py.

Barrido al boot (critico D-082 follow-up): cualquier job que quede en
estado queued/running de un proceso anterior se marca `failed` con evento
"interrumpido por reinicio". Sin esto, el guard 409 (`find_active`) bloquea
para siempre re-disparar ese kind+proyecto.

Logs: el texto completo del log NO va en `jobs` (puede ser MB). Se guarda
como evento final `type="log_tail"` con los ultimos LOG_TAIL_LINES del
buffer de memoria, al terminar el job (done/failed). El historial puede
mostrar esas ultimas lineas.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..telemetry import LEDGER_PATH

# Cuantas lineas del log final persisten por job (evita MB en SQLite).
LOG_TAIL_LINES = 200

_SCHEMA_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    project TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    ended_at REAL,
    result TEXT,
    error TEXT,
    scope TEXT NOT NULL DEFAULT 'batch'
);
"""

# Migracion defensiva: agrega la columna scope si la tabla ya existe sin ella
# (bases SQLite de Ciclos 1-3 no la tienen). ALTER TABLE es idempotente aqui
# porque se captura el error si la columna ya existe.
_MIGRATE_SCOPE = "ALTER TABLE jobs ADD COLUMN scope TEXT NOT NULL DEFAULT 'batch'"

# Kinds que son SIEMPRE micro-iteraciones por item (independientemente del project)
_MICRO_KINDS = frozenset({"pose_variants", "shots"})

_SCHEMA_JOB_EVENTS = """
CREATE TABLE IF NOT EXISTS job_events (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT ''
);
"""


def determine_scope(kind: str, project: str) -> str:
    """Determina el scope de un job: 'batch' o 'item'.

    Regla: es 'item' si el project contiene '/' (jobs por-escena/personaje/pose
    usan project='slug/sub') O si el kind es un micro-kind (pose_variants, shots).
    En cualquier otro caso es 'batch'.
    """
    if kind in _MICRO_KINDS or "/" in project:
        return "item"
    return "batch"


def _open(db_path: Path) -> sqlite3.Connection:
    """Abre (o crea) la base y garantiza las tablas de jobs.

    `check_same_thread=False` porque FastAPI despacha requests en el mismo
    proceso pero potencialmente en threads distintos (TestClient lo hace).
    El acceso real del server es single-threaded asyncio, asi que no hay
    contention real en produccion; en tests el flag evita el ProgrammingError.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA_JOBS)
    conn.execute(_SCHEMA_JOB_EVENTS)
    # Migracion defensiva: bases anteriores no tienen la columna scope.
    try:
        conn.execute(_MIGRATE_SCOPE)
    except sqlite3.OperationalError:
        pass  # la columna ya existe — idempotente
    conn.commit()
    return conn


class JobStore:
    """Capa de persistencia de jobs sobre SQLite (misma base que telemetry D-079).

    Unico responsable de: crear tablas, registrar transiciones, hacer el
    barrido al boot y responder consultas de historial.
    """

    def __init__(self, db_path: Path = LEDGER_PATH):
        self._db_path = db_path  # expuesto para tests de aislamiento
        self._conn = _open(db_path)

    # --- escritura -----------------------------------------------------------

    def insert_job(self, job_id: str, kind: str, project: str,
                   created_at: float | None = None,
                   scope: str | None = None) -> None:
        """Registra un nuevo job (estado queued) + su evento inicial.

        `scope` se puede pasar explicitamente; si es None se calcula con
        `determine_scope(kind, project)`.
        """
        now = created_at if created_at is not None else time.time()
        job_scope = scope if scope is not None else determine_scope(kind, project)
        self._conn.execute(
            """INSERT OR IGNORE INTO jobs
               (id, kind, project, status, created_at, scope)
               VALUES (?, ?, ?, 'queued', ?, ?)""",
            (job_id, kind, project, now, job_scope),
        )
        self._conn.execute(
            """INSERT INTO job_events (job_id, ts, type, payload)
               VALUES (?, ?, 'queued', '')""",
            (job_id, now),
        )
        self._conn.commit()

    def set_running(self, job_id: str, started_at: float | None = None) -> None:
        """Transicion queued -> running."""
        now = started_at if started_at is not None else time.time()
        self._conn.execute(
            """UPDATE jobs SET status='running', started_at=?
               WHERE id=? AND status='queued'""",
            (now, job_id),
        )
        self._conn.execute(
            """INSERT INTO job_events (job_id, ts, type, payload)
               VALUES (?, ?, 'running', '')""",
            (job_id, now),
        )
        self._conn.commit()

    def set_done(self, job_id: str, result: dict | None, *,
                 log_tail: list[str] | None = None,
                 ended_at: float | None = None) -> None:
        """Transicion running -> done."""
        self._set_terminal(job_id, "done",
                           result=result, error=None,
                           log_tail=log_tail, ended_at=ended_at)

    def set_failed(self, job_id: str, error: str, *,
                   log_tail: list[str] | None = None,
                   ended_at: float | None = None) -> None:
        """Transicion running|queued -> failed."""
        self._set_terminal(job_id, "failed",
                           result=None, error=error,
                           log_tail=log_tail, ended_at=ended_at)

    def _set_terminal(self, job_id: str, status: str,
                      result: dict | None, error: str | None,
                      log_tail: list[str] | None,
                      ended_at: float | None) -> None:
        now = ended_at if ended_at is not None else time.time()
        result_json = json.dumps(result) if result is not None else None
        self._conn.execute(
            """UPDATE jobs
               SET status=?, ended_at=?, result=?, error=?
               WHERE id=?""",
            (status, now, result_json, error, job_id),
        )
        self._conn.execute(
            """INSERT INTO job_events (job_id, ts, type, payload)
               VALUES (?, ?, ?, ?)""",
            (job_id, now, status, error or ""),
        )
        # Persistir el tail del log como evento separado para historial
        if log_tail:
            tail = log_tail[-LOG_TAIL_LINES:]
            self._conn.execute(
                """INSERT INTO job_events (job_id, ts, type, payload)
                   VALUES (?, ?, 'log_tail', ?)""",
                (job_id, now, json.dumps(tail)),
            )
        self._conn.commit()

    # --- barrido al boot (CRITICO) -------------------------------------------

    def sweep_interrupted(self, interrupted_at: float | None = None) -> list[str]:
        """Marca como failed todos los jobs queued/running del proceso anterior.

        Debe llamarse en el __init__ del JobManager, ANTES de que lleguen
        requests, para que `find_active` no bloquee re-disparar jobs huerfanos.
        Devuelve los ids barridos (utiles para tests y logs).
        """
        now = interrupted_at if interrupted_at is not None else time.time()
        rows = self._conn.execute(
            "SELECT id FROM jobs WHERE status IN ('queued', 'running')"
        ).fetchall()
        ids = [r["id"] for r in rows]
        if not ids:
            return ids
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"""UPDATE jobs
               SET status='failed', ended_at=?,
                   error='interrumpido por reinicio del servidor'
               WHERE id IN ({placeholders})""",
            [now, *ids],
        )
        for jid in ids:
            self._conn.execute(
                """INSERT INTO job_events (job_id, ts, type, payload)
                   VALUES (?, ?, 'failed', 'interrumpido por reinicio del servidor')""",
                (jid, now),
            )
        self._conn.commit()
        return ids

    # --- consultas -----------------------------------------------------------

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Devuelve la fila de `jobs` + el log_tail si existe, o None."""
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        # Decodificar result JSON
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except Exception:
                pass
        # Adjuntar log_tail del ultimo evento de ese tipo
        tail_row = self._conn.execute(
            """SELECT payload FROM job_events
               WHERE job_id=? AND type='log_tail'
               ORDER BY rowid DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if tail_row:
            try:
                d["log_tail"] = json.loads(tail_row["payload"])
            except Exception:
                d["log_tail"] = []
        else:
            d["log_tail"] = []
        return d

    def list_history(self, limit: int = 50, offset: int = 0,
                     since: float | None = None,
                     kind: str | list[str] | None = None,
                     scope: str | None = None,
                     include_micro: bool = False) -> list[dict[str, Any]]:
        """Jobs terminados (done/failed), mas nuevos primero, paginado.

        `since`        : Unix timestamp — solo jobs terminados despues de ese momento.
        `kind`         : filtrar por kind (str o lista de strings).
        `scope`        : filtrar por scope exacto ('batch' o 'item').
        `include_micro`: si False (default) excluye los jobs scope='item'.
                         Si True los incluye todos. `scope` explicito tiene prioridad.
        """
        params: list[Any] = []
        query = """SELECT id, kind, project, status,
                          created_at, started_at, ended_at, result, error, scope
                   FROM jobs
                   WHERE status IN ('done', 'failed')"""
        if since is not None:
            query += " AND ended_at > ?"
            params.append(since)
        # Filtro por scope: `scope` explicito tiene prioridad sobre include_micro
        if scope is not None:
            query += " AND scope = ?"
            params.append(scope)
        elif not include_micro:
            query += " AND scope = 'batch'"
        # Filtro por kind (uno o varios)
        if kind is not None:
            if isinstance(kind, str):
                kinds = [k.strip() for k in kind.split(",") if k.strip()]
            else:
                kinds = list(kind)
            if kinds:
                placeholders = ",".join("?" * len(kinds))
                query += f" AND kind IN ({placeholders})"
                params.extend(kinds)
        query += " ORDER BY ended_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            if d.get("result"):
                try:
                    d["result"] = json.loads(d["result"])
                except Exception:
                    pass
            out.append(d)
        return out

    def close(self) -> None:
        self._conn.close()
