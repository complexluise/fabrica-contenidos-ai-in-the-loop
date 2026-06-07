"""Build orquestado: `pyinstaller` + bundle post-build + zip opcional.

Pensado para correr tanto en dev local (Windows/Mac/Linux) como en CI
(GitHub Actions). Una sola entrada, una sola salida: el bundle distribuible.

Uso:
  python scripts/build.py             # build basico
  python scripts/build.py --zip       # + zip para GitHub Release
  python scripts/build.py --skip-install  # no re-sincroniza deps
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "pipeline.spec"


def run(cmd: list[str], **kw) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", action="store_true")
    parser.add_argument("--skip-install", action="store_true",
                       help="No corre `uv sync`; usa el venv tal cual.")
    parser.add_argument("--clean", action="store_true",
                       help="Borra dist/ y build/ antes de empezar.")
    args = parser.parse_args()

    if not SPEC.exists():
        sys.exit(f"[build] no encuentro {SPEC}")

    if not args.skip_install:
        # Sincroniza deps con los extras que necesita el binario (apis, studio).
        run(["uv", "sync", "--extra", "apis", "--extra", "studio", "--extra", "dev"])
        # PyInstaller es dev-only; no lo agregamos a pyproject deps.
        run(["uv", "pip", "install", "pyinstaller"])

    if args.clean:
        for d in (ROOT / "dist", ROOT / "build"):
            if d.exists():
                shutil.rmtree(d)
                print(f"[build] cleaned: {d.relative_to(ROOT)}")

    run(["uv", "run", "pyinstaller", str(SPEC), "--noconfirm"])

    bundle_cmd = [sys.executable, str(ROOT / "scripts" / "bundle.py")]
    if args.zip:
        bundle_cmd.append("--zip")
    run(bundle_cmd)

    print("[build] OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
