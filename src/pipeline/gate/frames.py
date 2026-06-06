"""Extracción de un frame representativo del clip (para CLIP/aesthetic/VLM).

I/O ffmpeg -> no unit-test; se valida con smoke run.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def extract_frame(video_path: Path, at_seconds: float = 1.0) -> Path:
    """Extrae un frame a `at_seconds` y devuelve el PNG. Lanza si falla ffmpeg."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg no está en el PATH (necesario para el gate).")
    out = Path(tempfile.gettempdir()) / f"frame_{abs(hash(str(video_path))) & 0xFFFFFF:06x}.png"
    subprocess.run(
        [ff, "-y", "-ss", str(at_seconds), "-i", str(video_path), "-frames:v", "1", str(out)],
        check=True, capture_output=True,
    )
    return out
