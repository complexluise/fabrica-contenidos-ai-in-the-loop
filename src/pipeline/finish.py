"""L7.5 - Finishing: el "film stock" en ffmpeg (D-073). $0 por corrida.

Lo que separa el output de los top creators del nuestro NO es solo el modelo:
es la capa de post que matan el "plástico digital" (el colorista del ad de
Porsche con Veo gradea cada clip exactamente para eso) y el grano que unifica
tomas de generaciones distintas ("35mm grain al 10-15% reduce la detección de
AI hasta 40%", Green Frog Labs). Todo implementable con ffmpeg.

El ORDEN de la cadena es load-bearing (funciona como un node tree de Resolve):

    balance -> look (curva S + saturación) -> vignette -> halation -> sharpen
    -> GRANO (último op visual) -> loudnorm two-pass (audio)

- vignette ANTES de halation: un brillo puede "glowear" sobre el borde viñeteado
  (lee como real); grano DESPUÉS de todo: textura uniforme encima del film.
- grano temporal (allf=t+u), nunca estático; el encode lleva -tune grain o el
  códec se lo come.
- loudnorm a -14 LUFS / -1.0 dBTP (spec IG/TikTok); two-pass linear=true para
  no comprimir dinámica (single-pass comprime, documentado).

Builders puros (testeables) + `apply_finish` (I/O ffmpeg, smoke).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from .config import FinishConfig  # noqa: F401 — re-export (D-077)

logger = logging.getLogger(__name__)


# FinishConfig vive en config.py (D-077): la capa de config no depende de
# un modulo de procesamiento. Se re-exporta aca por compatibilidad.


# --- builders puros -----------------------------------------------------------

def film_look_filter(fc: FinishConfig) -> str:
    """La cadena visual completa como -filter_complex (pura, testeable).

    Cada efecto se puede apagar desde el estilo (grain=0, halation_alpha=0,
    vignette=false) y el op se OMITE — el orden de los presentes no cambia."""
    base_ops: list[str] = [
        f"eq=saturation={fc.saturation}:contrast={fc.contrast}",
        f"curves=master='{fc.curve}'",
    ]
    if fc.vignette:
        base_ops.append("vignette=angle=PI/5")
    chain = ",".join(base_ops)

    post_ops: list[str] = []
    if fc.sharpen > 0:
        post_ops.append(f"unsharp=5:5:{fc.sharpen}")
    if fc.grain > 0:
        # Grano TEMPORAL (t+u): cambia por frame, como el de verdad.
        post_ops.append(f"noise=alls={fc.grain}:allf=t+u")
    post = ("," + ",".join(post_ops)) if post_ops else ""

    if fc.halation_alpha > 0:
        # Halation: keyear highlights altos -> blur grande -> tinte cálido ->
        # screen blend sutil. Estructura int10h + receta de coloristas (LGG).
        return (
            f"[0:v]{chain},split[base][forglow];"
            f"[forglow]lutyuv=y='clip((val-{fc.halation_threshold})*4,0,255)',"
            f"gblur=sigma={fc.halation_sigma}:steps=4,"
            f"colorchannelmixer=rr=1.0:gg=0.55:bb=0.35[hal];"
            f"[base][hal]blend=all_mode=screen:all_opacity={fc.halation_alpha}[glowed];"
            f"[glowed]null{post}[vout]"
        )
    return f"[0:v]{chain}{post}[vout]"


def speed_filters(speed: float, fps: int = 24) -> tuple[str, str]:
    """Filtros (video, audio) del conformado de velocidad (pura).

    1.10-1.30x es el fix documentado de la flotación AI; a 1.0 solo conforma
    fps (cadencias mezcladas entre generaciones también son un tell)."""
    if speed and speed != 1.0:
        return (f"setpts=PTS/{speed},fps={fps}", f"atempo={speed}")
    return (f"fps={fps}", "")


def parse_loudnorm_json(stderr: str) -> dict | None:
    """Extrae el JSON de medición que loudnorm imprime en stderr (pura)."""
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def loudnorm_measure_filter(lufs: float = -14.0, true_peak: float = -1.0) -> str:
    """Pasada 1: medir (print_format=json a stderr). Pura."""
    return f"loudnorm=I={lufs:g}:TP={true_peak:g}:LRA=11:print_format=json"


def loudnorm_apply_filter(measured: dict, lufs: float = -14.0,
                          true_peak: float = -1.0) -> str:
    """Pasada 2: aplicar con los valores medidos, modo LINEAL (pura).

    linear=true preserva la dinámica (la pasada única comprime — documentado);
    pasarse del target activa el limitador de la plataforma, que aplasta todo."""
    return (
        f"loudnorm=I={lufs:g}:TP={true_peak:g}:LRA=11:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )


# --- I/O (ffmpeg real; se valida con smoke, no unit) ---------------------------

def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def apply_finish(src: Path, out: Path, fc: FinishConfig) -> Path:
    """Aplica el film stock completo al film ya ensamblado (I/O, best-effort).

    Pasada A: cadena visual + medición loudnorm; Pasada B: loudnorm lineal con
    lo medido. Si algo falla, devuelve `src` intacto (el finishing nunca tumba
    un render — mismo contrato best-effort que captions/música)."""
    from .assemble import ffmpeg_exe, has_audio

    out.parent.mkdir(parents=True, exist_ok=True)
    graded = out.parent / f"_{out.stem}_graded.mp4"

    # Pasada A: look visual (+ medir loudnorm si hay audio, mismo decode).
    cmd = [ffmpeg_exe(), "-y", "-i", str(src),
           "-filter_complex", film_look_filter(fc), "-map", "[vout]"]
    has_audio = has_audio(src)
    if has_audio:
        cmd += ["-map", "0:a", "-af", loudnorm_measure_filter(fc.lufs, fc.true_peak),
                "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-tune", "grain",  # sin esto el códec se come el grano
            "-pix_fmt", "yuv420p", str(graded)]
    proc = _run(cmd)
    if proc.returncode != 0 or not graded.exists():
        logger.warning("finishing: fallo el grade (se entrega sin film stock): %s",
                       (proc.stderr or "")[-400:])
        return src

    if not has_audio:
        graded.replace(out)
        return out

    measured = parse_loudnorm_json(proc.stderr or "")
    if not measured:
        logger.warning("finishing: loudnorm no midio; se entrega con grade y sin mastering.")
        graded.replace(out)
        return out

    # Pasada B: mastering lineal con los valores medidos (video ya listo: copy).
    cmd2 = [ffmpeg_exe(), "-y", "-i", str(graded),
            "-af", loudnorm_apply_filter(measured, fc.lufs, fc.true_peak),
            "-c:v", "copy", "-c:a", "aac", str(out)]
    proc2 = _run(cmd2)
    if proc2.returncode != 0 or not out.exists():
        logger.warning("finishing: fallo el mastering (se entrega con grade): %s",
                       (proc2.stderr or "")[-400:])
        graded.replace(out)
        return out
    graded.unlink(missing_ok=True)
    return out


def conform_speed(clip: Path, out: Path, speed: float, fps: int = 24) -> Path:
    """Conforma velocidad/cadencia de UN clip (I/O). Best-effort: fallo -> original."""
    from .assemble import ffmpeg_exe, has_audio

    out.parent.mkdir(parents=True, exist_ok=True)
    vf, af = speed_filters(speed, fps)
    cmd = [ffmpeg_exe(), "-y", "-i", str(clip), "-vf", vf]
    if af and has_audio(clip):
        cmd += ["-af", af]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(out)]
    proc = _run(cmd)
    if proc.returncode != 0 or not out.exists():
        logger.warning("conform_speed: fallo (%sx); se usa el clip original.", speed)
        return clip
    return out
