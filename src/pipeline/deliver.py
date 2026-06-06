"""L8 - Entrega: reframe al formato de salida (MVP: 9:16).

Multi-formato simultaneo queda en backlog. Aqui reescala/recorta al aspect ratio
objetivo con ffmpeg.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assemble import _ffmpeg

# Resoluciones objetivo por formato.
_FORMATS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}


def reframe(src: Path, out_path: Path, fmt: str = "9:16") -> Path:
    """Recorta/escala el video al formato objetivo (crop centrado + scale)."""
    if fmt not in _FORMATS:
        raise ValueError(f"Formato no soportado: {fmt}. Usa {list(_FORMATS)}.")
    w, h = _FORMATS[fmt]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}"
    )
    cmd = [
        _ffmpeg(), "-y", "-i", str(src), "-vf", vf,
        "-c:a", "copy", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
