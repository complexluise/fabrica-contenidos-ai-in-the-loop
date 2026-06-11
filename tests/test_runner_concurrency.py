"""Core: concurrencia de escenas en run_project (D-039).

Verifica que:
- Los clips salen en el orden de las escenas aunque corran en paralelo (AC3).
- Una escena que falla no aborta el resto del run (AC4).

`_render_shot` se mockea para no tocar APIs ni disco de verdad.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.contracts import Scene
from pipeline.project import Project, ProjectSpec
from pipeline.runner import run_project


def _make_spec(n: int) -> ProjectSpec:
    scenes = [Scene(id=f"s{i}", prompt=f"escena {i}", duration_s=2) for i in range(n)]
    return ProjectSpec(slug="test", style="lego", format="9:16", scenes=scenes)


def _make_project(tmp_path: Path) -> Project:
    proj = Project(slug="test", root=tmp_path)
    proj.dir.mkdir(parents=True)
    (proj.dir / "storyboard.signed").write_text("", encoding="utf-8")
    return proj


def _make_cfg(routing_rules: dict | None = None):
    from pipeline.config import Config, KeyframeConfig, ProviderConfig, RoutingConfig, StrategyRule, StyleConfig
    rules = routing_rules or {
        "standard": StrategyRule(strategy="router", providers=["fake"]),
    }
    routing = RoutingConfig(rules=rules, thresholds={
        "standard": {"aesthetic": 0.5, "char_consistency": 0.5, "clip_adherence": 0.5},
    })
    provider = ProviderConfig(name="fake", backend="fal", model="fake/model",
                              cost_per_second=0.0, capabilities={"i2v"})
    style = StyleConfig(
        style="lego",
        keyframe=KeyframeConfig(backend="fal", model="fake/kf"),
        prompt_template="{scene_prompt}",
    )
    return Config(providers={"fake": provider}, routing=routing, style=style)


# Fake SceneRecord liviano (solo los campos que telemetry.record necesita).
def _fake_record(shot_id: str):
    rec = MagicMock()
    rec.shot_id = shot_id
    return rec


async def _render_shot_ok(**kwargs):
    """Mock de _render_shot: devuelve un clip con el shot_id en el nombre.

    Tupla de 6 (D-048/A2): clip, record, manifest, audio, keyframe, kf_key.
    """
    shot_id = kwargs["shot_id"]
    clip = Path(f"/fake/{shot_id}.mp4")
    return clip, _fake_record(shot_id), {"shot_id": shot_id}, False, Path(f"/fake/{shot_id}.png"), f"kf_{shot_id}"


async def _render_shot_fail_s1(**kwargs):
    """Mock: la escena s1 siempre falla."""
    if kwargs["scene"].id == "s1":
        raise RuntimeError("fallo forzado s1")
    return await _render_shot_ok(**kwargs)


# run_project necesita que concat_clips y reframe existan; los mockeamos a nivel modulo.
_MOCK_PATCHES = [
    "pipeline.runner.concat_clips",
    "pipeline.runner.reframe",
    "pipeline.runner.add_run_logfile",
    "pipeline.runner.remove_handler",
    "pipeline.runner.KeyframeGenerator",
    "pipeline.runner.Telemetry",
    "pipeline.runner.FusedGate",
    "pipeline.runner.build_provider",
]


def _apply_patches(monkeypatch):
    for target in _MOCK_PATCHES:
        monkeypatch.setattr(target, MagicMock())
    # concat_clips y reframe devuelven un Path para que el runner no explote
    import pipeline.runner as rmod
    rmod.concat_clips.return_value = Path("/fake/stitched.mp4")
    rmod.reframe.return_value = Path("/fake/final_9x16.mp4")
    telemetry_inst = MagicMock()
    telemetry_inst.totals.return_value = {"total_cost_usd": 0.0, "cache_hits": 0, "attempts": 0}
    rmod.Telemetry.return_value = telemetry_inst


async def test_clips_en_orden_con_concurrencia(tmp_path, monkeypatch):
    """AC3: con concurrency>1, los clips salen en el orden de las escenas."""
    _apply_patches(monkeypatch)

    # Intercalamos delays distintos para forzar que las escenas terminen fuera de orden.
    execution_order = []

    async def _render_with_delay(**kwargs):
        scene_id = kwargs["scene"].id
        delay = 0.05 if scene_id == "s0" else 0.01  # s1 termina antes que s0
        await asyncio.sleep(delay)
        execution_order.append(scene_id)
        return await _render_shot_ok(**kwargs)

    with patch("pipeline.runner._render_shot", side_effect=_render_with_delay):
        proj = _make_project(tmp_path)
        spec = _make_spec(3)
        cfg = _make_cfg()
        await run_project(proj, spec, cfg, concurrency=3)

    import pipeline.runner as rmod
    clips_passed = rmod.concat_clips.call_args[0][0]
    # Los clips deben estar en el orden s0, s1, s2 (orden de escenas en el spec).
    names = [c.name for c in clips_passed]
    assert names == ["s0.mp4", "s1.mp4", "s2.mp4"]


async def test_escena_fallida_no_aborta_run(tmp_path, monkeypatch):
    """AC4: una escena que falla con concurrency>1 no aborta las demas."""
    _apply_patches(monkeypatch)

    with patch("pipeline.runner._render_shot", side_effect=_render_shot_fail_s1):
        proj = _make_project(tmp_path)
        spec = _make_spec(3)  # s0, s1 (falla), s2
        cfg = _make_cfg()
        # No debe lanzar excepcion (s0 y s2 salvan el run)
        await run_project(proj, spec, cfg, concurrency=2)

    import pipeline.runner as rmod
    clips_passed = rmod.concat_clips.call_args[0][0]
    names = [c.name for c in clips_passed]
    assert "s0.mp4" in names and "s2.mp4" in names
    assert "s1.mp4" not in names
