"""Core: backend de voz seleccionable (D-058) — patrón D-053.

Hoy el TTS se elegía implícitamente por presencia de key (`if elevenlabs else fal`).
Ahora es un backend configurable y persistido: kokoro (prototipo) / elevenlabs
(producción), elegible como `storyboard_backend`. Lógica pura/config -> core.
"""

from pathlib import Path

from pipeline.audio import select_tts_backend
from pipeline.config import load_voice_config
from pipeline.project import spec_from_dict, spec_to_dict

CONFIG_DIR = Path("config")


# --- select_tts_backend (lógica pura de elección + degradación) -------------

def test_select_uses_requested_when_its_key_present():
    assert select_tts_backend("elevenlabs", has_elevenlabs=True, has_fal=True) == "elevenlabs"
    assert select_tts_backend("kokoro", has_elevenlabs=True, has_fal=True) == "kokoro"


def test_select_degrades_to_available_when_requested_key_missing():
    # pide elevenlabs sin su key -> cae al único disponible (kokoro); voz best-effort
    assert select_tts_backend("elevenlabs", has_elevenlabs=False, has_fal=True) == "kokoro"
    # pide kokoro sin fal -> cae a elevenlabs
    assert select_tts_backend("kokoro", has_elevenlabs=True, has_fal=False) == "elevenlabs"


def test_select_none_when_no_keys():
    assert select_tts_backend("kokoro", has_elevenlabs=False, has_fal=False) is None
    assert select_tts_backend("elevenlabs", has_elevenlabs=False, has_fal=False) is None


# --- load_voice_config (presets de routing.yaml) ----------------------------

def test_load_voice_config_kokoro_is_default_proto():
    vc = load_voice_config(CONFIG_DIR / "routing.yaml", backend="kokoro")
    assert vc.backend == "kokoro"
    assert vc.default_voice  # cada motor trae su voz por defecto


def test_load_voice_config_elevenlabs_is_production():
    vc = load_voice_config(CONFIG_DIR / "routing.yaml", backend="elevenlabs")
    assert vc.backend == "elevenlabs"


def test_load_voice_config_unknown_falls_back_to_kokoro():
    vc = load_voice_config(CONFIG_DIR / "routing.yaml", backend="inexistente")
    assert vc.backend == "kokoro"


# --- round-trip de voice_backend en el spec (persistencia, patrón D-053) ----

def test_spec_voice_backend_roundtrip():
    spec = spec_from_dict(
        {"scenes": [{"id": "s1", "prompt": "p", "duration_s": 2}], "voice_backend": "elevenlabs"},
        "t",
    )
    assert spec.voice_backend == "elevenlabs"
    assert spec_to_dict(spec)["voice_backend"] == "elevenlabs"


def test_spec_voice_backend_default_kokoro_not_serialized():
    spec = spec_from_dict({"scenes": [{"id": "s1", "prompt": "p", "duration_s": 2}]}, "t")
    assert spec.voice_backend == "kokoro"        # default = lo más barato (D-052)
    assert "voice_backend" not in spec_to_dict(spec)  # default no ensucia el yaml
