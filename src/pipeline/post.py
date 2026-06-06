"""L7 - Post de marca: lower-thirds / títulos por plantilla (ffmpeg drawtext).

El constructor del filtro es lógica pura (testeable). El burn con ffmpeg es I/O
(smoke). Auto-captions (whisper) quedan diferidas: casi todos los clips son mudos
salvo Veo.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def default_font() -> str | None:
    """Una fuente del sistema (Windows suele necesitar fontfile en drawtext)."""
    for candidate in (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _escape_drawtext(text: str) -> str:
    """Escapa los caracteres especiales de drawtext (\\, :, ')."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def lower_third_filter(
    text: str,
    fontsize: int = 48,
    fontcolor: str = "white",
    margin: int = 80,
    box: bool = True,
) -> str:
    """Construye el filtro drawtext para un lower-third centrado abajo."""
    t = _escape_drawtext(text)
    box_opts = ":box=1:boxcolor=black@0.5:boxborderw=20" if box else ""
    return (
        f"drawtext=text='{t}':fontsize={fontsize}:fontcolor={fontcolor}"
        f":x=(w-tw)/2:y=h-th-{margin}{box_opts}"
    )


def burn_lower_third(src: Path, out: Path, text: str, fontfile: str | None = None, **kw) -> Path:
    """Quema un lower-third en el video. `fontfile` puede ser necesario en Windows."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg no está en el PATH.")
    vf = lower_third_filter(text, **kw)
    if fontfile:
        vf = vf.replace("drawtext=", f"drawtext=fontfile='{_escape_drawtext(fontfile)}':", 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-i", str(src), "-vf", vf, "-c:a", "copy", str(out)],
        check=True, capture_output=True,
    )
    return out
