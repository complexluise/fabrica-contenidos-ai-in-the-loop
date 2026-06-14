"""L9 - Telemetria de costo y latencia por escena.

No es opcional ni diferible: es lo que valida el ahorro 60-70% que justifica
todo el diseno y lo que permite recalibrar el router. Persiste a SQLite y emite
un run_report.json por corrida.

D-079: la base SQLite es UN LIBRO MAYOR GLOBAL (`out/telemetry.sqlite`), no un
archivo por run — "cuanto llevo gastado, en que proveedor, en que proyecto" se
responde con `costs_summary` / `pipeline costs`. El run_report.json por corrida
sigue siendo el manifiesto inmutable del run.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# D-079: el libro mayor de costos — global, gitignoreado, compartido por TODOS
# los proyectos y runs. Un solo lugar donde mirar la plata.
LEDGER_PATH = Path("out/telemetry.sqlite")


@dataclass
class SceneRecord:
    """Una linea de telemetria por escena (puede haber varios intentos)."""

    run_id: str
    scene_id: str
    provider: str
    strategy: str
    scene_class: str
    cost_usd: float
    latency_s: float
    project: str = ""  # D-079: el slug del proyecto (lo sella Telemetry)
    attempt: int = 1
    passed: bool = True
    cached: bool = False  # True si salio del cache (costo 0)
    keyframe_key: str = ""
    video_key: str = ""
    audio_provider: str = ""   # paso de post de audio (V2A MMAudio, D-034); "" si no hubo
    audio_cost_usd: float = 0.0  # costo del V2A (0 en cache hit o si no aplica)
    keyframe_cost_usd: float = 0.0  # costo de generacion del keyframe (flux-lora; 0 en cache hit)
    tts_cost_usd: float = 0.0  # costo de voz en off (ElevenLabs o kokoro; 0 si no hubo VO)
    ts: float = field(default_factory=time.time)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS scene_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    scene_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    strategy TEXT NOT NULL,
    scene_class TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    latency_s REAL NOT NULL,
    attempt INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    cached INTEGER NOT NULL,
    keyframe_key TEXT NOT NULL,
    video_key TEXT NOT NULL,
    audio_provider TEXT NOT NULL DEFAULT '',
    audio_cost_usd REAL NOT NULL DEFAULT 0,
    keyframe_cost_usd REAL NOT NULL DEFAULT 0,
    tts_cost_usd REAL NOT NULL DEFAULT 0,
    ts REAL NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Migracion minima del libro mayor (D-079): agrega `project` si falta.

    Los sqlite pre-D-079 (uno por run) siguen siendo legibles si se consultan;
    sus filas viejas quedan con project='' (sin proyecto)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(scene_runs)")}
    if cols and "project" not in cols:
        conn.execute("ALTER TABLE scene_runs ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        conn.commit()


class Telemetry:
    """Registro de costo/latencia de UN run, contra el libro mayor global (D-079)."""

    def __init__(self, run_id: str, db_path: Path | None = None, project: str = ""):
        # db_path se resuelve aqui (no en la firma) para que monkeypatch de
        # LEDGER_PATH en tests sea efectivo (default lazy, no early-bind).
        resolved = Path(db_path) if db_path is not None else LEDGER_PATH
        self.run_id = run_id
        self.db_path = resolved
        self.project = project  # D-079: se sella en cada record
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(resolved)
        _migrate(self._conn)
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._records: list[SceneRecord] = []
        self._failures: list[dict] = []  # escenas que fallaron (robustez, Sprint 5)

    def record_failure(self, scene_id: str, error: str) -> None:
        """Registra una escena fallida sin abortar el run."""
        self._failures.append({"scene_id": scene_id, "error": error})

    def record(self, rec: SceneRecord) -> None:
        if not rec.project and self.project:  # D-079: el run sella su proyecto
            rec.project = self.project
        self._records.append(rec)
        self._conn.execute(
            """INSERT INTO scene_runs
               (run_id, project, scene_id, provider, strategy, scene_class,
                cost_usd, latency_s, attempt, passed, cached,
                keyframe_key, video_key, audio_provider, audio_cost_usd,
                keyframe_cost_usd, tts_cost_usd, ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec.run_id, rec.project, rec.scene_id, rec.provider, rec.strategy,
                rec.scene_class,
                rec.cost_usd, rec.latency_s, rec.attempt, int(rec.passed), int(rec.cached),
                rec.keyframe_key, rec.video_key, rec.audio_provider, rec.audio_cost_usd,
                rec.keyframe_cost_usd, rec.tts_cost_usd, rec.ts,
            ),
        )
        self._conn.commit()

    def totals(self) -> dict:
        """Agrega totales de la corrida (los del objeto en memoria)."""
        video_cost   = sum(r.cost_usd for r in self._records)
        audio_cost   = sum(r.audio_cost_usd for r in self._records)
        kf_cost      = sum(r.keyframe_cost_usd for r in self._records)
        tts_cost     = sum(r.tts_cost_usd for r in self._records)
        total_cost   = video_cost + audio_cost + kf_cost + tts_cost
        total_latency = sum(r.latency_s for r in self._records)
        by_provider: dict[str, float] = {}
        for r in self._records:
            by_provider[r.provider] = by_provider.get(r.provider, 0.0) + r.cost_usd
            if r.audio_provider and r.audio_cost_usd:
                by_provider[r.audio_provider] = by_provider.get(r.audio_provider, 0.0) + r.audio_cost_usd
            if r.keyframe_cost_usd:
                by_provider["flux-lora (keyframe)"] = by_provider.get("flux-lora (keyframe)", 0.0) + r.keyframe_cost_usd
            if r.tts_cost_usd:
                by_provider["tts"] = by_provider.get("tts", 0.0) + r.tts_cost_usd
        return {
            "run_id": self.run_id,
            "scenes": len({r.scene_id for r in self._records}),
            "attempts": len(self._records),
            "cache_hits": sum(1 for r in self._records if r.cached),
            "failed_scenes": len(self._failures),
            "total_cost_usd": round(total_cost, 4),
            "cost_breakdown": {
                "video_usd": round(video_cost, 4),
                "keyframe_usd": round(kf_cost, 4),
                "sfx_usd": round(audio_cost, 4),
                "tts_usd": round(tts_cost, 4),
            },
            "total_latency_s": round(total_latency, 2),
            "cost_by_provider": {k: round(v, 4) for k, v in by_provider.items()},
        }

    def write_report(self, path: Path = Path("out/run_report.json")) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "summary": self.totals(),
            "scenes": [asdict(r) for r in self._records],
            "failures": self._failures,
        }
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path

    def close(self) -> None:
        self._conn.close()


# --- D-079: consultas del libro mayor ----------------------------------------

def _record_total(rec: SceneRecord) -> float:
    """Costo TOTAL de una fila: video + sfx + keyframe + tts. Pura."""
    return rec.cost_usd + rec.audio_cost_usd + rec.keyframe_cost_usd + rec.tts_cost_usd


def costs_summary(db_path: Path | None = None, days: int | None = None,
                  project: str | None = None) -> dict:
    """Cuanto se ha gastado: total, desglose, por proyecto y por proveedor.

    Lee el libro mayor (D-079). `days` limita a los ultimos N dias; `project`
    filtra a un slug. Sin ledger -> resumen en ceros (nunca lanza)."""
    # db_path se resuelve aqui (no en la firma) para que monkeypatch de
    # LEDGER_PATH en tests sea efectivo (default lazy, no early-bind).
    db_path = Path(db_path) if db_path is not None else LEDGER_PATH
    empty = {"total_usd": 0.0, "runs": 0, "scenes": 0,
             "breakdown": {"video_usd": 0.0, "sfx_usd": 0.0, "keyframe_usd": 0.0,
                            "tts_usd": 0.0},
             "by_project": {}, "by_provider": {},
             "days": days, "project": project}
    if not db_path.exists():
        return empty

    field_names = [f.name for f in fields(SceneRecord)]
    query = f"SELECT {', '.join(field_names)} FROM scene_runs WHERE 1=1"
    params: list = []
    if days is not None:
        query += " AND ts >= ?"
        params.append(time.time() - days * 86400)
    if project is not None:
        query += " AND project = ?"
        params.append(project)

    conn = sqlite3.connect(db_path)
    try:
        _migrate(conn)  # ledgers pre-D-079: las filas viejas cuentan (project='')
        # Defensivo: la base puede existir (creada por JobStore) sin scene_runs todavia.
        tables = {row[1] for row in conn.execute("PRAGMA table_info(scene_runs)")}
        if not tables:
            return empty
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    if not rows:
        return empty

    records = [SceneRecord(**dict(zip(field_names, row))) for row in rows]
    by_project: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    video = sfx = kf = tts = 0.0
    for r in records:
        by_project[r.project] = by_project.get(r.project, 0.0) + _record_total(r)
        by_provider[r.provider] = by_provider.get(r.provider, 0.0) + r.cost_usd
        if r.audio_provider and r.audio_cost_usd:
            by_provider[r.audio_provider] = (by_provider.get(r.audio_provider, 0.0)
                                             + r.audio_cost_usd)
        video += r.cost_usd
        sfx += r.audio_cost_usd
        kf += r.keyframe_cost_usd
        tts += r.tts_cost_usd
    return {
        "total_usd": round(video + sfx + kf + tts, 4),
        "runs": len({r.run_id for r in records}),
        "scenes": len(records),
        "breakdown": {"video_usd": round(video, 4), "sfx_usd": round(sfx, 4),
                       "keyframe_usd": round(kf, 4), "tts_usd": round(tts, 4)},
        "by_project": {k: round(v, 4) for k, v in sorted(by_project.items(),
                                                          key=lambda kv: -kv[1])},
        "by_provider": {k: round(v, 4) for k, v in sorted(by_provider.items(),
                                                           key=lambda kv: -kv[1])},
        "days": days, "project": project,
    }
