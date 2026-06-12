"""L7 - Audio: voz en off (ElevenLabs) y mezcla con ffmpeg (Sprint 6).

La parte de arriba es lógica pura (resolución de voz, autocompletado de caption,
inputs del cache) -> core testeable. La parte de abajo es I/O con ffmpeg (mezcla
de la VO en el clip) -> se valida con smoke, no con unit tests.

Decisión: voz multilingüe por defecto (contenido en español) + override por escena
sobre el default del proyecto. Ver [[prefer-apis-over-heavy-libs]].
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assemble import ffmpeg_exe, has_audio
from .contracts import Scene

# Voz stock multilingüe de ElevenLabs ("Rachel"); se cambia en el project.yaml
# (`voice_id:`) o por escena. El modelo multilingüe cubre el español.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
# eleven_turbo_v2_5: multilingüe (español ok), ~40% mas barato que multilingual_v2.
# Para maxima calidad cambiarlo a "eleven_multilingual_v2".
DEFAULT_VOICE_MODEL = "eleven_turbo_v2_5"

# Cuánto baja el audio diegético del clip (sfx/ambiente, D-034) cuando hay voz
# en off encima. Jerarquía: voz 1.0 > diegético 0.6 > música 0.25 (en assemble).
DIEGETIC_DUCK = 0.6


def resolve_voice(voice_id: str | None, spec, default: str | None = None) -> str:
    """Voz efectiva: la del plano/escena (`voice_id`, ya resuelta por
    `effective_voice`) > default del proyecto > default del motor de voz activo
    (D-058) > default del sistema. D-075: recibe el voice_id explícito en vez de
    un objeto-escena (el job de render ya no viaja disfrazado de Scene)."""
    return voice_id or getattr(spec, "voice_id", None) or default or DEFAULT_VOICE_ID


def select_tts_backend(name: str, *, has_elevenlabs: bool, has_fal: bool) -> str | None:
    """Motor de TTS efectivo (D-058): formaliza la elección antes implícita por key.

    Devuelve el backend pedido (`name`) si su credencial está; si no, **degrada** al
    otro motor disponible (la voz es best-effort: nunca bloquea el render). Si no hay
    ninguna credencial, `None` (se renderiza sin voz). Lógica pura, testeable."""
    available = {"elevenlabs": has_elevenlabs, "kokoro": has_fal}
    if available.get(name):
        return name
    return next((engine for engine, ok in available.items() if ok), None)


def effective_caption(shot) -> str | None:
    """Caption a quemar: la explícita; si no hay, se autocompleta con la VO (Sprint 6).

    Como el humano ya escribe el texto de la voz en off, no hace falta whisper.
    Acepta Shot o Scene (ambos tienen caption/voiceover)."""
    if shot.caption:
        return shot.caption
    return shot.voiceover or None


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


def mux_cmds(clip, voice, out, clip_has_audio: bool,
             diegetic_volume: float = DIEGETIC_DUCK, exe: str = "ffmpeg") -> list[str]:
    """Comando ffmpeg del mux de VO (pura, testeable). EL VIDEO MANDA LA DURACIÓN
    en AMBAS ramas (D-078): `duration=first` en el amix (rama diegética) y
    `-shortest` en la rama muda. Sin `-shortest`, una VO más larga que el plano
    estiraba el clip y DESINCRONIZABA todo el film aguas abajo del concat
    (verificado con ffmpeg: un film de 4s salía de 6s). La VO que no cabe se
    corta — exactamente lo que el advisory `vo_too_long` promete al firmar."""
    if clip_has_audio:
        return [
            exe, "-y", "-i", str(clip), "-i", str(voice),
            "-filter_complex", vo_mix_filter(diegetic_volume),
            "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out),
        ]
    return [
        exe, "-y", "-i", str(clip), "-i", str(voice),
        "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out),
    ]


def mux_voiceover(clip: Path, voice: Path, out: Path,
                  diegetic_volume: float = DIEGETIC_DUCK) -> Path:
    """Pone la VO en el clip. El video manda la duración (D-078; ver `mux_cmds`).

    - Clip **con** audio diegético (sfx/ambiente de MMAudio o nativo, D-034):
      **mezcla** la VO encima, bajando el diegético (`amix`), no lo reemplaza.
    - Clip **mudo** (sin audio): la VO se vuelve su pista de audio, recortada
      al final del video (`-shortest`).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = mux_cmds(clip, voice, out, has_audio(clip), diegetic_volume, exe=ffmpeg_exe())
    subprocess.run(cmd, check=True, capture_output=True)
    return out
