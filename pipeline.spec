# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para `video-gen-pipeline` (D-XXX: bundle distribuible).

Genera `dist/pipeline/pipeline.exe` (Windows) / `dist/pipeline/pipeline` (Unix)
mas una carpeta `_internal/` con Python + deps. El entry es
`src/pipeline/__main__.py`, que sin args abre la GUI Tkinter y con args va
a la CLI Typer.

Decisiones:
  - onedir (no onefile): el .exe se baja como un .zip y se extrae una vez;
    arranques posteriores son instantaneos (no re-extrae a temp).
  - console=True: la GUI tambien escribe a consola (util para diagnostico);
    en Windows el .exe abre su propia ventana de consola al doble-click.
  - include-data de `config/` y `projects/la-fractura/` (workspace ejemplo);
    `scripts/bundle.py` los copia al lado del .exe para que el launcher los
    encuentre con `Path(sys.executable).parent`.
  - ffmpeg.exe (Windows) se bundlea como binario.
  - `collect_submodules("pipeline")` descubre TODOS los submódulos (incluido
    `pipeline.server.app` que se importa solo en runtime al lanzar Studio).
    Mantener una lista manual de hiddenimports es fragil.

Uso:
  pyinstaller pipeline.spec --noconfirm
  python scripts/bundle.py   # copia workspace/ al lado del .exe
"""
from pathlib import Path
import shutil
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

ROOT = Path(SPECPATH).resolve()  # SPECPATH lo inyecta PyInstaller
SRC = ROOT / "src"


def _collect_tree(disk_dir: Path, dest_in_bundle: str) -> list[tuple[str, str]]:
    """Devuelve la lista de (source, dest) para todos los archivos bajo disk_dir,
    preservando la estructura relativa bajo `dest_in_bundle/` en el bundle.
    Equivalente a `Tree()` que fue removido en PyInstaller 6."""
    if not disk_dir.exists():
        return []
    out: list[tuple[str, str]] = []
    for p in disk_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(disk_dir.parent)
            out.append((str(p), str(rel)))
    return out


datas: list[tuple[str, str]] = []
datas += _collect_tree(ROOT / "config", "config")
datas += _collect_tree(ROOT / "projects" / "lego_mix", "projects/lego_mix")

# Bundlea ffmpeg.exe (Windows) si esta en PATH — sino lo busca `bundle.py` aparte.
binaries: list[tuple[str, str]] = []
ffmpeg_bin = shutil.which("ffmpeg")
if ffmpeg_bin and sys.platform.startswith("win"):
    binaries.append((ffmpeg_bin, "."))


a = Analysis(
    # Top-level wrapper (no en el paquete) para que PyInstaller no lo trate
    # como `__main__` y rompa los relative imports dentro de `pipeline.*`.
    [str(ROOT / "scripts" / "_bundle_entry.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=collect_submodules("pipeline"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Recorta el bundle: cosas pesadas que no usamos (torch queda en
        # `vision` extra, dev esta fuera del .exe).
        "torch", "torchvision", "open_clip", "transformers",
        "pytest", "pytest_asyncio",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: los .pyd/.dll van a _internal/
    name="pipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX a veces rompe Tkinter en Windows; lo dejo off
    console=True,  # ventana de consola (util para pegar logs)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="pipeline",
)
