"""Core Sprint 6: voz en off (ElevenLabs).

Test-first. Lo que se testea es la LÓGICA pura (sin red ni ffmpeg):
- resolución de voz (override por escena > default de proyecto > default del sistema),
- autocompletado de la caption desde el texto de la VO,
- el cache key de la VO (estable + sensible a texto/voz/modelo),
- el parseo de `voiceover`/`voice_id` desde el project.yaml.

El adapter de ElevenLabs (HTTP) y la mezcla con ffmpeg se validan con smoke, no aquí.
"""

from pathlib import Path

import yaml

from pipeline.audio import (
    DEFAULT_VOICE_ID,
    DEFAULT_VOICE_MODEL,
    effective_caption,
    resolve_voice,
    vo_inputs,
)
from pipeline.contracts import Scene
from pipeline.project import ProjectSpec, cache_key, load_project_spec


# --- resolve_voice ----------------------------------------------------------

def _spec(voice_id=None, scenes=None):
    return ProjectSpec(slug="p", style="lego", format="9:16",
                       scenes=scenes or [], voice_id=voice_id)


def test_resolve_voice_scene_override_wins():
    # D-075: resolve_voice recibe el voice_id efectivo, no un objeto-escena.
    scene = Scene(id="s", prompt="p", duration_s=4, voice_id="scene-voice")
    spec = _spec(voice_id="proj-voice")
    assert resolve_voice(scene.voice_id, spec) == "scene-voice"


def test_resolve_voice_falls_back_to_project_default():
    scene = Scene(id="s", prompt="p", duration_s=4)
    spec = _spec(voice_id="proj-voice")
    assert resolve_voice(scene.voice_id, spec) == "proj-voice"


def test_resolve_voice_falls_back_to_system_default():
    scene = Scene(id="s", prompt="p", duration_s=4)
    spec = _spec(voice_id=None)
    assert resolve_voice(scene.voice_id, spec) == DEFAULT_VOICE_ID


# --- effective_caption (autocompletado desde la VO) -------------------------

def test_effective_caption_prefers_explicit_caption():
    scene = Scene(id="s", prompt="p", duration_s=4,
                  caption="texto en pantalla", voiceover="texto narrado")
    assert effective_caption(scene) == "texto en pantalla"


def test_effective_caption_autofills_from_voiceover():
    scene = Scene(id="s", prompt="p", duration_s=4, voiceover="texto narrado")
    assert effective_caption(scene) == "texto narrado"


def test_effective_caption_none_when_neither():
    scene = Scene(id="s", prompt="p", duration_s=4)
    assert effective_caption(scene) is None


# --- cache key de la VO -----------------------------------------------------

def test_vo_cache_key_is_stable():
    a = cache_key("voiceover", vo_inputs("hola", "v1", "m1"))
    b = cache_key("voiceover", vo_inputs("hola", "v1", "m1"))
    assert a == b


def test_vo_cache_key_changes_with_text_voice_and_model():
    base = cache_key("voiceover", vo_inputs("hola", "v1", "m1"))
    assert cache_key("voiceover", vo_inputs("otra cosa", "v1", "m1")) != base
    assert cache_key("voiceover", vo_inputs("hola", "v2", "m1")) != base
    assert cache_key("voiceover", vo_inputs("hola", "v1", "m2")) != base


# --- parseo del project.yaml ------------------------------------------------

def test_load_project_spec_parses_voiceover_and_voice(tmp_path: Path):
    data = {
        "project": "demo",
        "style": "lego",
        "voice_id": "proj-voice",
        "scenes": [
            {"id": "s1", "prompt": "una ciudad", "duration_s": 5,
             "voiceover": "Una ciudad despierta al amanecer."},
            {"id": "s2", "prompt": "un parque", "duration_s": 5,
             "voiceover": "Juan camina tranquilo.", "voice_id": "otra-voz"},
        ],
    }
    p = tmp_path / "project.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    spec = load_project_spec(p)

    assert spec.voice_id == "proj-voice"
    assert spec.scenes[0].voiceover == "Una ciudad despierta al amanecer."
    assert spec.scenes[0].voice_id is None
    assert spec.scenes[1].voice_id == "otra-voz"
    # el modelo por defecto soporta multilingüe (español)
    assert "multilingual" in DEFAULT_VOICE_MODEL or "turbo" in DEFAULT_VOICE_MODEL


# --- D-078: el video manda la duracion en AMBAS ramas del mux -----------------

def test_mux_cmds_mute_clip_video_rules_duration():
    """Rama muda: sin -shortest, una VO mas larga que el plano estiraba el clip
    y DESINCRONIZABA todo el film aguas abajo del concat (verificado: film de
    4s salia de 6s). El video manda."""
    from pipeline.audio import mux_cmds

    cmd = mux_cmds("c.mp4", "v.mp3", "o.mp4", clip_has_audio=False)
    assert "-shortest" in cmd


def test_mux_cmds_diegetic_branch_mixes_video_first():
    from pipeline.audio import mux_cmds

    cmd = mux_cmds("c.mp4", "v.mp3", "o.mp4", clip_has_audio=True)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "duration=first" in fc          # el audio del CLIP manda la mezcla
    assert "-shortest" not in cmd          # amix ya gobierna; -shortest sobra
