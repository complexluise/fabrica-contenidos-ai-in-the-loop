"""Core: el router decide el costo de toda la produccion. Critico.

Regla: el provider mas BARATO que cumple las capabilities exigidas.
"""

import pytest

from pipeline.contracts import SceneRequirements, ShotJob
from pipeline.strategies.router import pick_provider
from conftest import make_provider


def _job(req: SceneRequirements | None = None) -> ShotJob:
    return ShotJob(id="s", prompt="p", duration_s=4, requirements=req or SceneRequirements())


def test_picks_cheapest_when_all_eligible():
    providers = [
        make_provider("kling", 0.03, {"i2v"}),
        make_provider("seedance", 0.06, {"i2v", "multishot"}),
    ]
    assert pick_provider(_job(), providers).name == "kling"


def test_skips_provider_missing_capability():
    # Escena con audio: kling no tiene 'audio', debe ir a veo aunque sea mas caro.
    providers = [
        make_provider("kling", 0.03, {"i2v", "lipsync"}),
        make_provider("veo", 0.50, {"i2v", "audio", "lipsync"}),
    ]
    job = _job(SceneRequirements(needs_audio=True))
    assert pick_provider(job, providers).name == "veo"


def test_raises_when_no_provider_qualifies():
    providers = [make_provider("kling", 0.03, {"i2v"})]
    job = _job(SceneRequirements(needs_hdr=True))
    with pytest.raises(ValueError):
        pick_provider(job, providers)
