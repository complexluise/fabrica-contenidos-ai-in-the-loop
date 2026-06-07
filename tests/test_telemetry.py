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
