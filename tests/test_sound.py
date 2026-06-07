"""Core Sprint 6.9: diseño sonoro — SFX + ambiente (D-034).

Test-first del core puro: parseo/round-trip de `scene.ambience` + `shot.sfx`,
`effective_audio_cue` (sfx del plano + ambiente de la escena) e inputs/filtro de
mezcla. La generación V2A (MMAudio) y la mezcla ffmpeg se validan con smoke.
"""

from pipeline.audio import effective_audio_cue, sfx_inputs, vo_mix_filter
from pipeline.contracts import Scene, Shot
from pipeline.project import load_project_spec, write_spec


def _scene(**kw):
    base = dict(id="s1", prompt="ciudad", duration_s=5)
    base.update(kw)
    return Scene(**base)


# --- T6.9.1: parseo + round-trip de los campos nuevos -----------------------

def test_scene_parses_ambience_and_shot_sfx(tmp_path):
    f = tmp_path / "project.yaml"
    f.write_text(
        "project: p\nstyle: lego\nscenes:\n"
        "  - id: s1\n    prompt: ciudad\n    duration_s: 6\n    ambience: trafico lejano\n"
        "    shots:\n"
        "      - framing: portazo\n        duration_s: 3\n        sfx: golpe de puerta\n"
        "      - framing: pasos\n        duration_s: 3\n",
        encoding="utf-8",
    )
    sc = load_project_spec(f).scenes[0]
    assert sc.ambience == "trafico lejano"
    assert sc.shots[0].sfx == "golpe de puerta"
    assert sc.shots[1].sfx is None


def test_write_spec_round_trips_sound_fields(tmp_path):
    src = tmp_path / "src.yaml"
    src.write_text(
        "project: p\nstyle: lego\nscenes:\n"
        "  - id: s1\n    prompt: ciudad\n    duration_s: 4\n    ambience: viento\n"
        "    shots:\n      - framing: x\n        duration_s: 4\n        sfx: trueno\n",
        encoding="utf-8",
    )
    spec = load_project_spec(src)
    reloaded = load_project_spec(write_spec(spec, tmp_path / "out.yaml"))
    assert reloaded == spec
    text = (tmp_path / "out.yaml").read_text(encoding="utf-8")
    assert "ambience: viento" in text and "sfx: trueno" in text


def test_sound_fields_default_none():
    assert _scene().ambience is None
    assert Shot(duration_s=3).sfx is None


# --- T6.9.2: effective_audio_cue --------------------------------------------

def test_cue_combines_sfx_then_ambience():
    sc = _scene(ambience="tráfico de ciudad")
    sh = Shot(framing="portazo", duration_s=3, sfx="golpe de puerta")
    assert effective_audio_cue(sc, sh) == "golpe de puerta, tráfico de ciudad"


def test_cue_only_sfx():
    assert effective_audio_cue(_scene(), Shot(duration_s=3, sfx="paso")) == "paso"


def test_cue_only_ambience():
    assert effective_audio_cue(_scene(ambience="bosque"), Shot(duration_s=3)) == "bosque"


def test_cue_none_when_empty():
    assert effective_audio_cue(_scene(), Shot(duration_s=3)) is None
    assert effective_audio_cue(_scene(ambience="  "), Shot(duration_s=3, sfx="")) is None


# --- T6.9.5: inputs de caché + filtro de mezcla -----------------------------

def test_sfx_inputs_deterministic_and_seed_aware():
    a = sfx_inputs("lluvia", "mmaudio", seed=0)
    assert a == sfx_inputs("lluvia", "mmaudio", seed=0)
    assert a != sfx_inputs("lluvia", "mmaudio", seed=1)


def test_vo_mix_filter_ducks_diegetic_and_amixes():
    f = vo_mix_filter(0.6)
    assert "volume=0.6" in f and "amix=inputs=2" in f
