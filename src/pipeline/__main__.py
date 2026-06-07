"""Entry point del binario.

Comportamiento:
  - `pipeline` (sin args)         -> abre la GUI (Tkinter, ver `launcher.py`).
  - `pipeline <subcmd> ...`        -> delega a la CLI Typer (`cli.app`).

Esto permite distribuir UN SOLO binario: el .exe que se baja el no-tecnico
abre la GUI con doble-click, y el dev que corre `uv run pipeline render ...`
desde la terminal sigue teniendo la CLI completa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_bundled_runtime_on_path() -> None:
    """El bundle PyInstaller onedir mete `ffmpeg.exe` y otros binarios en
    `_internal/`, fuera del PATH del usuario. Sin esto, `shutil.which("ffmpeg")`
    falla y el render no puede ensamblar video. Lo agregamos al PATH antes
    de cualquier import del pipeline.

    En dev (`uv run`) el directorio `_internal/` no existe; el helper es no-op.
    """
    exe_dir = Path(sys.executable).resolve().parent
    internal = exe_dir / "_internal"
    if not internal.is_dir():
        return
    sep = os.pathsep
    cur = os.environ.get("PATH", "")
    internal_str = str(internal)
    if internal_str not in cur.split(sep):
        os.environ["PATH"] = internal_str + sep + cur


_ensure_bundled_runtime_on_path()


def main() -> int:
    if len(sys.argv) == 1:
        # Importes absolutos (no `from .launcher`): en el binario frozen,
        # el contexto de paquete no esta establecido y los relative imports
        # fallan con "attempted relative import with no known parent package".
        from pipeline.launcher import launch_gui
        return launch_gui()
    from pipeline.cli import app
    app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
