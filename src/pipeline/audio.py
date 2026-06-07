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

from .assemble import _has_audio
from .contracts import Scene

# Voz stock multilingüe de ElevenLabs ("Rachel"); se cambia en el project.yaml
# (`voice_id:`) o por escena. El modelo multilingüe cubre el español.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_VOICE_MODEL = "eleven_multilingual_v2"

# Cuánto baja el audio diegético del clip (sfx/ambiente, D-034) cuando hay voz
# en off encima. Jerarquía: voz 1.0 > diegético 0.6 > música 0.25 (en assemble).
DIEGETIC_DUCK = 0.6


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


def effective_audio_cue(scene: Scene, shot) -> str | None:
    """Cue de diseño sonoro de un plano (D-034): SFX del plano (la acción) +
    ambiente de la escena (el lugar). None si no hay nada. Lógica pura.

    El SFX va primero (primer plano sonoro), el ambiente después (bed del lugar).
    """
    parts = [p.strip() for p in (shot.sfx, scene.ambience) if p and p.strip()]
    return ", ".join(parts) if parts else None


def sfx_inputs(cue: str, model: str, seed: int = 0) -> dict:
    """Inputs que llavean el audio diegético V2A (mismo clip+cue+modelo -> cache hit).

    El clip ya está fijado por `video_key` aguas arriba; aquí va lo que agrega el
    paso V2A: el cue de texto, el modelo y el seed (reroll del audio del plano).
    """
    return {"cue": cue, "model": model, "seed": seed}


def vo_mix_filter(diegetic_volume: float = DIEGETIC_DUCK) -> str:
    """Filtro ffmpeg (D-034): baja el audio diegético del clip y le mezcla la VO
    encima. Así la narración queda por encima del sfx/ambiente, no lo reemplaza."""
    return (f"[0:a]volume={diegetic_volume}[d];"
            f"[d][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]")


# --- mezcla con ffmpeg (I/O) ------------------------------------------------


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg no está en el PATH. Instálalo para mezclar audio.")
    return exe


def mux_voiceover(clip: Path, voice: Path, out: Path,
                  diegetic_volume: float = DIEGETIC_DUCK) -> Path:
    """Pone la VO en el clip (el video manda la duración). No usa `-shortest`.

    - Clip **con** audio diegético (sfx/ambiente de MMAudio o nativo, D-034):
      **mezcla** la VO encima, bajando el diegético (`amix`), no lo reemplaza.
    - Clip **mudo** (sin audio): la VO se vuelve su pista de audio (como antes).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if _has_audio(clip):
        cmd = [
            _ffmpeg(), "-y", "-i", str(clip), "-i", str(voice),
            "-filter_complex", vo_mix_filter(diegetic_volume),
            "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out),
        ]
    else:
        cmd = [
            _ffmpeg(), "-y", "-i", str(clip), "-i", str(voice),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out),
        ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out
