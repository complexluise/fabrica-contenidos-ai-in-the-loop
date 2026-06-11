"""L7 - Ensamblaje y post: concat de clips + audio/musica via ffmpeg.

ffmpeg como motor (rapido, gratis, control total). Desde Sprint 6 los clips
pueden traer voz en off, asi que el audio se normaliza antes de concatenar (todos
con una pista aac uniforme, silencio si no hay) y la musica se mezcla *por debajo*
(ducking via amix) en vez de reemplazar el audio.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg no esta en el PATH. Instalalo para ensamblar.")
    return exe


def _has_audio(clip: Path) -> bool:
    """True si el clip tiene al menos una pista de audio (via ffprobe)."""
    probe = shutil.which("ffprobe")
    if not probe:
        return False
    out = subprocess.run(
        [probe, "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def _video_sig(clip: Path) -> tuple[str, int, int] | None:
    """Firma de video del clip: (codec, ancho, alto) via ffprobe, o None.

    Sirve para decidir si el concat por demuxer (-c copy) es seguro: solo lo es
    cuando todos los clips comparten codec+resolucion.
    """
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    out = subprocess.run(
        [probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    )
    parts = out.stdout.strip().split(",")
    if len(parts) < 3:
        return None
    try:
        return (parts[0], int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _uniform(sigs: list[tuple[str, int, int] | None]) -> bool:
    """True si los clips comparten firma de video (concat -c copy es seguro).

    Conservador: si alguna firma es None (ffprobe ausente) no podemos afirmar
    heterogeneidad, asi que asumimos uniforme y conservamos el codec (rapido).
    """
    known = [s for s in sigs if s is not None]
    return len(set(known)) <= 1


def _canonical_size(sigs: list[tuple[str, int, int] | None]) -> tuple[int, int] | None:
    """Resolucion canonica para conformar clips mezclados: la de mayor area.

    Escalar hacia la mas grande evita perder resolucion del mejor clip; los demas
    se letterboxean (pad) para no distorsionar.
    """
    known = [s for s in sigs if s is not None]
    if not known:
        return None
    w, h = max(known, key=lambda s: s[1] * s[2])[1:3]
    return (w, h)


def _normalize(clip: Path, out: Path, video_size: tuple[int, int] | None = None) -> Path:
    """Normaliza el clip a una pista aac estereo 44100 (silencio si no tenia).

    Necesario para que el concat por demuxer (-c copy) sea uniforme cuando unos
    clips traen voz en off y otros no. Si `video_size` se da, ademas conforma el
    video a un codec/resolucion canonicos (libx264, letterbox sin distorsion):
    indispensable cuando se mezclan clips de varios providers con codec/resolucion
    distintos, donde `-c copy` produciria video roto en silencio (D-054). Sin
    `video_size`, el video se COPIA (rapido; caso 1 provider, comportamiento previo).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if video_size is None:
        vfilter: list[str] = []
        vcodec = ["-c:v", "copy"]
    else:
        w, h = video_size
        vfilter = ["-vf", (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")]
        vcodec = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if _has_audio(clip):
        cmd = [_ffmpeg(), "-y", "-i", str(clip),
               *vfilter, *vcodec, "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)]
    else:
        cmd = [_ffmpeg(), "-y",
               "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-i", str(clip),
               *vfilter, "-map", "1:v:0", "-map", "0:a", *vcodec, "-c:a", "aac",
               "-shortest", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _probe_duration(clip: Path) -> float | None:
    """Duración del clip en segundos (via ffprobe), o None si no se puede medir."""
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    out = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except (ValueError, TypeError):
        return None


def trim_to(clip: Path, out: Path, duration_s: float) -> Path:
    """Recorta el clip a `duration_s` SOLO si es más largo (D-028, conservador).

    Para cuando el provider impone un mínimo (p.ej. ~5s) y el plano pide menos. Si
    ffprobe no está o el clip ya cabe, devuelve el clip original (no re-encode).
    """
    dur = _probe_duration(clip)
    if dur is None or dur <= duration_s + 0.1:
        return clip
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-i", str(clip), "-t", f"{duration_s}",
           "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def last_frame_cmd(clip: Path, out: Path) -> list[str]:
    """Comando ffmpeg para extraer el ÚLTIMO frame del clip (pura, testeable).

    `-sseof -0.1` busca desde el final (rápido, sin decodificar todo); `-update 1`
    sobreescribe hasta quedarse con el último frame decodificado de ese tramo."""
    return [_ffmpeg(), "-y", "-sseof", "-0.1", "-i", str(clip),
            "-frames:v", "1", "-update", "1", "-q:v", "2", str(out)]


def extract_last_frame(clip: Path, out: Path) -> Path:
    """Extrae el último frame real del clip (D-059): el frame-inicio del plano
    siguiente en la cinta pixel-real. Fallback: si el seek desde el final no
    produce salida (clip cortísimo), decodifica entero y se queda con el último."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(last_frame_cmd(clip, out), check=False, capture_output=True)
    if not out.exists():
        cmd = [_ffmpeg(), "-y", "-i", str(clip), "-update", "1", "-q:v", "2", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
    return out


def concat_clips(clips: list[Path], out_path: Path, music: Path | None = None,
                 music_volume: float = 1.0) -> Path:
    """Concatena clips en orden. Opcionalmente mezcla musica de fondo (ducked).

    `music_volume` < 1 baja la musica para que la voz en off quede por encima.
    """
    if not clips:
        raise ValueError("No hay clips para ensamblar.")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Audio uniforme antes de concatenar (algunos clips traen VO, otros no) y,
    # si los clips son heterogeneos (varios providers: codec/resolucion distintos),
    # tambien video uniforme: sin esto el demuxer -c copy rompe el video (D-054).
    norm_dir = out_path.parent / "_norm"
    norm_dir.mkdir(parents=True, exist_ok=True)
    sigs = [_video_sig(c) for c in clips]
    video_size = None if _uniform(sigs) else _canonical_size(sigs)
    norm_clips = [_normalize(c, norm_dir / f"{i:03d}.mp4", video_size)
                  for i, c in enumerate(clips)]

    # Lista para el demuxer concat de ffmpeg.
    list_file = out_path.parent / "_concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{c.resolve().as_posix()}'" for c in norm_clips), encoding="utf-8"
    )

    concat_out = out_path if music is None else out_path.parent / "_concat_tmp.mp4"
    cmd = [
        _ffmpeg(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(concat_out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    if music is not None:
        # Mezcla la musica POR DEBAJO del audio del video (VO/silencio), no lo reemplaza.
        fil_complex = (
            f"[1:a]volume={music_volume}[m];"
            f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        cmd = [
            _ffmpeg(), "-y", "-i", str(concat_out), "-i", str(music),
            "-filter_complex", fil_complex,
            "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        concat_out.unlink(missing_ok=True)

    list_file.unlink(missing_ok=True)
    return out_path
