"""L9 - Telemetria de costo y latencia por escena.

No es opcional ni diferible: es lo que valida el ahorro 60-70% que justifica
todo el diseno y lo que permite recalibrar el router. Persiste a SQLite y emite
un run_report.json por corrida.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
    attempt: int = 1
    passed: bool = True
    cached: bool = False  # True si salio del cache (costo 0)
    keyframe_key: str = ""
    video_key: str = ""
    audio_provider: str = ""   # paso de post de audio (V2A MMAudio, D-034); "" si no hubo
    audio_cost_usd: float = 0.0  # costo del V2A (0 en cache hit o si no aplica)
    ts: float = field(default_factory=time.time)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS scene_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
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
    ts REAL NOT NULL
);
"""


class Telemetry:
    """Registro de costo/latencia. Una instancia por corrida (run)."""

    def __init__(self, run_id: str, db_path: Path = Path("out/telemetry.sqlite")):
        self.run_id = run_id
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._records: list[SceneRecord] = []
        self._failures: list[dict] = []  # escenas que fallaron (robustez, Sprint 5)

    def record_failure(self, scene_id: str, error: str) -> None:
        """Registra una escena fallida sin abortar el run."""
        self._failures.append({"scene_id": scene_id, "error": error})

    def record(self, rec: SceneRecord) -> None:
        self._records.append(rec)
        self._conn.execute(
            """INSERT INTO scene_runs
               (run_id, scene_id, provider, strategy, scene_class,
                cost_usd, latency_s, attempt, passed, cached,
                keyframe_key, video_key, audio_provider, audio_cost_usd, ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec.run_id,
                rec.scene_id,
                rec.provider,
                rec.strategy,
                rec.scene_class,
                rec.cost_usd,
                rec.latency_s,
                rec.attempt,
                int(rec.passed),
                int(rec.cached),
                rec.keyframe_key,
                rec.video_key,
                rec.audio_provider,
                rec.audio_cost_usd,
                rec.ts,
            ),
        )
        self._conn.commit()

    def totals(self) -> dict:
        """Agrega totales de la corrida (los del objeto en memoria)."""
        total_cost = sum(r.cost_usd + r.audio_cost_usd for r in self._records)
        total_latency = sum(r.latency_s for r in self._records)
        by_provider: dict[str, float] = {}
        for r in self._records:
            by_provider[r.provider] = by_provider.get(r.provider, 0.0) + r.cost_usd
            if r.audio_provider and r.audio_cost_usd:  # el V2A como su propia línea (D-034)
                by_provider[r.audio_provider] = by_provider.get(r.audio_provider, 0.0) + r.audio_cost_usd
        return {
            "run_id": self.run_id,
            "scenes": len({r.scene_id for r in self._records}),
            "attempts": len(self._records),
            "cache_hits": sum(1 for r in self._records if r.cached),
            "failed_scenes": len(self._failures),
            "total_cost_usd": round(total_cost, 4),
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
