"""Core: validacion de contratos. Entradas invalidas DEBEN fallar."""

import pytest
from pydantic import ValidationError

from pipeline.contracts import GenResult, Scene, SceneRequirements, ShotJob


def test_scene_requires_positive_duration():
    with pytest.raises(ValidationError):
        Scene(id="s1", prompt="x", duration_s=0)


def test_scene_class_alias_roundtrips():
    # El campo se llama class_ en Python pero 'class' en el YAML/JSON.
    s = Scene(id="s1", prompt="x", duration_s=4, **{"class": "hero"})
    assert s.class_ == "hero"


def test_required_capabilities_mapping():
    # i2v es la base siempre exigida (D-054); los flags suman sobre ella.
    req = SceneRequirements(needs_audio=True, needs_4k=True)
    assert req.required_capabilities() == {"i2v", "audio", "4k"}


def test_empty_requirements_still_need_i2v():
    # Sin flags, la escena sigue exigiendo i2v (todo el pipeline es image-to-video).
    assert SceneRequirements().required_capabilities() == {"i2v"}


def test_genresult_rejects_negative_cost():
    with pytest.raises(ValidationError):
        GenResult(video_path="a.mp4", provider="kling", cost_usd=-1, latency_s=1)


# --- D-075: ShotJob es el contrato del render; Scene es narrativa pura -------

def test_shotjob_requires_positive_duration():
    with pytest.raises(ValidationError):
        ShotJob(id="s1", prompt="x", duration_s=0)


def test_shotjob_carries_generation_knobs():
    job = ShotJob(id="s1.2", prompt="camera orbits", duration_s=3,
                  aspect="9:16", cfg_scale=0.5, negative_prompt="morphing")
    assert job.aspect == "9:16" and job.cfg_scale == 0.5


def test_scene_has_no_render_transients():
    """Los campos 'transitorios' (start_frame/negative_prompt/aspect/cfg_scale/
    character_refs) viven en ShotJob, no en el contrato narrativo (D-075)."""
    s = Scene(id="s1", prompt="x", duration_s=4)
    for transient in ("start_frame", "negative_prompt", "aspect", "cfg_scale",
                      "character_refs"):
        assert transient not in Scene.model_fields, transient
        assert not hasattr(s, transient), transient
