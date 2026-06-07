"""Top-level entry SOLO para el bundle PyInstaller (D-XXX).

Por que existe:
  - PyInstaller trata el entry como `__main__` (modulo top-level), entonces
    los relative imports (`from .launcher`) fallan con "no known parent package".
  - Este wrapper es un modulo top-level que importa el paquete `pipeline`
    explicitamente. Asi el contexto de paquete queda bien establecido y los
    relatives dentro del paquete funcionan.

En dev esto no se usa: `uv run pipeline` cae al script `pipeline.cli:app`
(declarado en pyproject.toml), y `python -m pipeline` cae a `__main__.py`.

Dispath:
  - sin args -> GUI Tkinter
  - con args -> CLI Typer
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

    En dev este archivo no se ejecuta; el helper es no-op si no hay _internal.
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
        from pipeline.launcher import launch_gui
        return launch_gui()
    from pipeline.cli import app
    app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
