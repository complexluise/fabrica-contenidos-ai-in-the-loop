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
    """Una fuente BOLD del sistema (los subtítulos IG piden peso, D-064)."""
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",     # Arial Bold
        "C:/Windows/Fonts/segoeuib.ttf",    # Segoe UI Bold
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
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


def wrap_caption(text: str, width: int = 18, max_lines: int = 3) -> str:
    """Envuelve el caption en líneas cortas legibles en vertical (D-064). Pura.

    drawtext no envuelve solo; un caption largo en una línea se sale del 9:16.
    Si no cabe en `max_lines`, se trunca con elipsis (el caption es apoyo, no prosa)."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;") + "…"
    return "\n".join(lines)


def caption_filter(textfile: Path, height: int = 1920, fontsize: int | None = None,
                   fontfile: str | None = None) -> str:
    """Filtro drawtext estilo Instagram (D-064). Pura.

    - `textfile=` en vez de `text=`: saltos de línea y acentos sin escaping frágil.
    - Bold blanco con BORDE grueso (nada de cajita negra translúcida).
    - Centrado en y≈0.72h: la zona segura sobre la UI de IG/TikTok (botones/caption).
    """
    size = fontsize or max(40, round(height / 26))  # ~74px en 1920
    border = max(4, size // 9)
    font = f"fontfile='{_escape_drawtext(fontfile)}':" if fontfile else ""
    return (
        f"drawtext={font}textfile='{_escape_drawtext(str(textfile))}'"
        f":fontsize={size}:fontcolor=white"
        f":borderw={border}:bordercolor=black"
        f":shadowx=0:shadowy={max(2, size // 18)}:shadowcolor=black@0.45"
        f":line_spacing={size // 5}:text_align=center"
        f":x=(w-tw)/2:y=h*0.72-th/2"
    )


def burn_lower_third(src: Path, out: Path, text: str, fontfile: str | None = None, **kw) -> Path:
    """Quema el caption estilo IG en el video (D-064). I/O (smoke).

    El texto envuelto viaja en un .txt sidecar (UTF-8) -> multilínea y acentos
    sin pelear con el escaping de drawtext."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg no está en el PATH.")
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = out.with_suffix(".caption.txt")
    txt.write_text(wrap_caption(text), encoding="utf-8")
    vf = caption_filter(txt, fontfile=fontfile, **kw)
    subprocess.run(
        [ff, "-y", "-i", str(src), "-vf", vf, "-c:a", "copy", str(out)],
        check=True, capture_output=True,
    )
    return out
