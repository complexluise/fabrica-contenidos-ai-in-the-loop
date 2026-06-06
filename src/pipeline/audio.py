"""L7 - Audio: voz en off (ElevenLabs) y mezcla con ffmpeg (Sprint 6).

La parte de arriba es lógica pura (resolución de voz, autocompletado de caption,
inputs del cache) -> core testeable. La parte de abajo es I/O con ffmpeg (mezcla
de la VO en el clip) -> se valida con smoke, no con unit tests.

Decisión: voz multilingüe por defecto (contenido en español) + override por escena
sobre el default del proyecto. Ver [[prefer-apis-over-heavy-libs]].
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .contracts import Scene

# Voz stock multilingüe de ElevenLabs ("Rachel"); se cambia en el project.yaml
# (`voice_id:`) o por escena. El modelo multilingüe cubre el español.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_VOICE_MODEL = "eleven_multilingual_v2"


def resolve_voice(scene: Scene, spec) -> str:
    """Voz efectiva: override por escena > default del proyecto > default del sistema."""
    return scene.voice_id or getattr(spec, "voice_id", None) or DEFAULT_VOICE_ID


def effective_caption(scene: Scene) -> str | None:
    """Caption a quemar: la explícita; si no hay, se autocompleta con la VO (Sprint 6).

    Como el humano ya escribe el texto de la voz en off, no hace falta whisper.
    """
    if scene.caption:
        return scene.caption
    return scene.voiceover or None


def vo_inputs(text: str, voice_id: str, model: str) -> dict:
    """Inputs que llavean el audio de la VO (mismo texto+voz+modelo -> cache hit)."""
    return {"text": text, "voice_id": voice_id, "model": model}


# --- mezcla con ffmpeg (I/O) ------------------------------------------------


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg no está en el PATH. Instálalo para mezclar audio.")
    return exe


def mux_voiceover(clip: Path, voice: Path, out: Path) -> Path:
    """Pone la VO como pista de audio del clip (el video manda la duración).

    Los clips suelen venir mudos; aquí la VO se vuelve su audio. No se usa
    `-shortest` para no recortar el video si la VO es más corta.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y", "-i", str(clip), "-i", str(voice),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out
