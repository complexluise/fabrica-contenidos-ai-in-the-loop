"""Core: la telemetria valida el ahorro. Costos/latencias deben agregarse bien."""

from pipeline.telemetry import SceneRecord, Telemetry


def _rec(scene_id, provider, cost, lat, **kw):
    return SceneRecord(
        run_id="r1", scene_id=scene_id, provider=provider, strategy="router",
        scene_class="standard", cost_usd=cost, latency_s=lat, **kw,
    )


def test_totals_sum_cost_and_latency(tmp_path):
    t = Telemetry("r1", db_path=tmp_path / "t.sqlite")
    t.record(_rec("s1", "kling", 0.12, 30))
    t.record(_rec("s2", "veo", 2.50, 60))
    totals = t.totals()
    assert totals["total_cost_usd"] == 2.62
    assert totals["total_latency_s"] == 90.0
    assert totals["scenes"] == 2
    assert totals["cost_by_provider"] == {"kling": 0.12, "veo": 2.5}
    t.close()


def test_audio_cost_counts_in_total_and_own_provider_line(tmp_path):
    # D-034: el costo del paso V2A (MMAudio) suma al total y aparece como su
    # propia línea en cost_by_provider (no se atribuye al provider de video).
    t = Telemetry("r1", db_path=tmp_path / "t.sqlite")
    t.record(_rec("s1", "kling", 0.12, 30, audio_provider="mmaudio", audio_cost_usd=0.005))
    totals = t.totals()
    assert totals["total_cost_usd"] == 0.125
    assert totals["cost_by_provider"] == {"kling": 0.12, "mmaudio": 0.005}
    t.close()


def test_record_failure_counts_in_totals(tmp_path):
    t = Telemetry("r1", db_path=tmp_path / "t.sqlite")
    t.record(_rec("s1", "kling", 0.12, 30))
    t.record_failure("s2", "kling devolvio 500")
    totals = t.totals()
    assert totals["failed_scenes"] == 1
    assert totals["scenes"] == 1  # solo la que salio bien
    t.close()


def test_no_failures_is_zero(tmp_path):
    t = Telemetry("r1", db_path=tmp_path / "t.sqlite")
    t.record(_rec("s1", "kling", 0.12, 30))
    assert t.totals()["failed_scenes"] == 0
    t.close()


def test_report_written_to_disk(tmp_path):
    t = Telemetry("r1", db_path=tmp_path / "t.sqlite")
    t.record(_rec("s1", "kling", 0.12, 30, attempt=2, passed=False))
    report = t.write_report(tmp_path / "run_report.json")
    assert report.exists()
    t.close()


# --- D-079: el libro mayor global -------------------------------------------

import sqlite3
import time

import pytest

from pipeline.telemetry import costs_summary


def _ledger_rec(run_id, project, scene_id, provider, cost, **kw):
    return SceneRecord(
        run_id=run_id, scene_id=scene_id, provider=provider, strategy="router",
        scene_class="standard", cost_usd=cost, latency_s=1.0, project=project, **kw,
    )


def test_ledger_accumulates_runs_of_distinct_projects(tmp_path):
    """Dos runs de dos proyectos escriben al MISMO sqlite; costs_summary agrega."""
    db = tmp_path / "ledger.sqlite"
    t1 = Telemetry("r1", db_path=db, project="esquiva")
    t1.record(_ledger_rec("r1", "esquiva", "s1", "kling", 0.12))
    t1.close()
    t2 = Telemetry("r2", db_path=db, project="otro")
    t2.record(_ledger_rec("r2", "otro", "s1", "kling", 0.08))
    t2.close()
    s = costs_summary(db)
    assert s["total_usd"] == pytest.approx(0.20)
    assert s["runs"] == 2
    assert s["by_project"] == {"esquiva": pytest.approx(0.12), "otro": pytest.approx(0.08)}


def test_telemetry_stamps_project_on_records(tmp_path):
    """El runner no necesita poner project en cada record: Telemetry lo sella."""
    db = tmp_path / "ledger.sqlite"
    t = Telemetry("r1", db_path=db, project="esquiva")
    t.record(_rec("s1", "kling", 0.12, 30))  # record SIN project
    t.close()
    s = costs_summary(db)
    assert s["by_project"] == {"esquiva": pytest.approx(0.12)}


def test_costs_summary_filters_by_project_and_days(tmp_path):
    db = tmp_path / "ledger.sqlite"
    t = Telemetry("r1", db_path=db, project="a")
    t.record(_ledger_rec("r1", "a", "s1", "kling", 0.10))
    t.record(_ledger_rec("r1", "a", "s2", "kling", 0.10,
                         ts=time.time() - 10 * 86400))  # hace 10 dias
    t.record(_ledger_rec("r2", "b", "s1", "veo", 1.00))
    t.close()
    assert costs_summary(db, project="a")["total_usd"] == pytest.approx(0.20)
    assert costs_summary(db, days=7)["total_usd"] == pytest.approx(1.10)  # el viejo queda fuera
    assert costs_summary(db, days=7, project="a")["total_usd"] == pytest.approx(0.10)


def test_costs_summary_total_includes_all_cost_components(tmp_path):
    db = tmp_path / "ledger.sqlite"
    t = Telemetry("r1", db_path=db, project="a")
    t.record(_ledger_rec("r1", "a", "s1", "kling", 0.10,
                         audio_cost_usd=0.005, keyframe_cost_usd=0.003, tts_cost_usd=0.002))
    t.close()
    s = costs_summary(db)
    assert s["total_usd"] == pytest.approx(0.11)
    assert s["breakdown"] == {"video_usd": pytest.approx(0.10), "sfx_usd": pytest.approx(0.005),
                              "keyframe_usd": pytest.approx(0.003), "tts_usd": pytest.approx(0.002)}


def test_costs_summary_empty_without_ledger(tmp_path):
    s = costs_summary(tmp_path / "no_existe.sqlite")
    assert s["total_usd"] == 0.0 and s["runs"] == 0


_OLD_SCHEMA = """
CREATE TABLE scene_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL, scene_id TEXT NOT NULL, provider TEXT NOT NULL,
    strategy TEXT NOT NULL, scene_class TEXT NOT NULL,
    cost_usd REAL NOT NULL, latency_s REAL NOT NULL,
    attempt INTEGER NOT NULL, passed INTEGER NOT NULL, cached INTEGER NOT NULL,
    keyframe_key TEXT NOT NULL, video_key TEXT NOT NULL,
    audio_provider TEXT NOT NULL DEFAULT '', audio_cost_usd REAL NOT NULL DEFAULT 0,
    keyframe_cost_usd REAL NOT NULL DEFAULT 0, tts_cost_usd REAL NOT NULL DEFAULT 0,
    ts REAL NOT NULL
);
"""


def test_ledger_migrates_pre_d079_schema(tmp_path):
    """Un sqlite viejo (sin columna project) se migra solo; sus filas cuentan."""
    db = tmp_path / "viejo.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO scene_runs (run_id, scene_id, provider, strategy, scene_class,"
        " cost_usd, latency_s, attempt, passed, cached, keyframe_key, video_key, ts)"
        " VALUES ('r0','s1','kling','router','standard',0.05,1.0,1,1,0,'','',?)",
        (time.time(),))
    conn.commit()
    conn.close()
    t = Telemetry("r1", db_path=db, project="nuevo")  # abre y migra
    t.record(_ledger_rec("r1", "nuevo", "s1", "kling", 0.10))
    t.close()
    s = costs_summary(db)
    assert s["total_usd"] == pytest.approx(0.15)
    assert s["runs"] == 2
    assert s["by_project"][""] == pytest.approx(0.05)  # lo viejo, sin proyecto
