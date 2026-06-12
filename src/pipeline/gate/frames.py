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
    # El nombre incluye `at_seconds`: varios frames del mismo clip (D-041, describe)
    # no deben pisarse entre sí.
    tag = f"{abs(hash(str(video_path))) & 0xFFFFFF:06x}_{int(round(at_seconds * 1000)):07d}"
    out = Path(tempfile.gettempdir()) / f"frame_{tag}.png"
    subprocess.run(
        [ff, "-y", "-ss", str(at_seconds), "-i", str(video_path), "-frames:v", "1", str(out)],
        check=True, capture_output=True,
    )
    return out


def frame_times(duration_s: float) -> list[float]:
    """Tiempos de muestreo para que el gate VEA el movimiento (D-069). Pura.

    3 muestras (inicio/medio/fin, lejos de los bordes) — suficiente para detectar
    morphing, deriva de identidad y movimiento roto sin pagar un video-LLM.
    Clips cortísimos: una sola muestra central."""
    if duration_s < 1.2:
        return [round(duration_s / 2, 3)]
    a = max(0.3, duration_s * 0.1)
    c = min(duration_s - 0.3, duration_s * 0.9)
    return [round(a, 3), round(duration_s / 2, 3), round(c, 3)]
