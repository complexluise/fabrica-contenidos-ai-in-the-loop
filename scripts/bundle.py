"""Post-build: deja el bundle listo para distribuir.

Que hace:
  1. `dist/pipeline/pipeline.exe` (o `pipeline` en Unix) ya esta — eso es
     PyInstaller.
  2. Este script crea `dist/pipeline/workspace/` copiando `config/` y
     `projects/la-fractura/` desde la raiz del repo. Asi el launcher
     `find_workspace_root()` los encuentra al lado del .exe.
  3. Tambien copia `.env.example` (template de secrets) y un `README.txt`
     de "como arrancar" pensado para el no-tecnico.
  4. Opcionalmente, si pasas `--zip`, zipea `dist/pipeline/` en
     `dist/video-gen-pipeline-<plat>-<ver>.zip` para GitHub Release.

Uso:
  python scripts/bundle.py            # deja dist/pipeline/ listo
  python scripts/bundle.py --zip      # ademas genera el .zip
"""
from __future__ import annotations

import argparse
import platform
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "pipeline"
VERSION = "0.1.0"


def ensure_built() -> None:
    if not DIST.exists():
        sys.exit(f"[bundle] no encuentro {DIST}. Corré `pyinstaller pipeline.spec` primero.")


def copy_workspace() -> None:
    """Copia `config/` y `projects/lego_mix/` (ejemplo) al lado del .exe."""
    targets = [
        (ROOT / "config", DIST / "config"),
        (ROOT / "projects" / "lego_mix", DIST / "projects" / "lego_mix"),
    ]
    for src, dst in targets:
        if not src.exists():
            print(f"[bundle] SKIP (no existe): {src}")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"[bundle] copiado: {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

    env_example = ROOT / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, DIST / ".env.example")
        print("[bundle] copiado: .env.example")


def write_readme() -> None:
    """README de 30 segundos para el no-tecnico."""
    readme = DIST / "README.txt"
    exe_name = "pipeline.exe" if platform.system() == "Windows" else "pipeline"
    readme.write_text(
        f"""Video Pipeline v{VERSION} — Inicio rapido
============================================

1. Doble-click en `{exe_name}`. Se abre una ventana.

2. La GUI detecta automaticamente el proyecto `lego_mix/` (incluido como
   ejemplo: 3 escenas, 17s, "Un dia en la ciudad LEGO"). Si queres usar
   otro proyecto, descompacta el zip y pone tu carpeta `projects/<tu-slug>/`
   en este mismo directorio.

3. Click en "Renderizar video". Ahi arranca. Vas a ver el log abajo.
   - Tarda 5-10 min la primera vez (genera keyframes y clips).
   - Re-corrida = cache hit = $0 y segundos.
   - Cuando termina, el video queda en
     `projects/lego_mix/runs/<run_id>/final_9x16.mp4`.

4. Para abrir el video: click en "Abrir carpeta del proyecto" -> busca la
   subcarpeta `runs/<run_id>/` -> `final_9x16.mp4`.

5. Para iterar (cambiar una toma, regenerar solo esa escena):
   - Click en "Abrir Studio (web)" -> se abre en tu navegador.
   - O desde la terminal: `{exe_name} keyframes lego_mix --n 4`

Secretos (API keys)
-------------------
La primera vez que lo corras, te va a pedir que crees un archivo `.env`
junto a `{exe_name}`. Copia `.env.example` a `.env` y completa tus keys
(FAL_KEY, ANTHROPIC_API_KEY). Sin eso, el pipeline no puede llamar a
las APIs de video.

Costos
------
Cada corrida fresca gasta entre $0.5-3 USD en APIs (fal.ai, Anthropic,
ElevenLabs). La cache es content-addressed: re-correr sin cambios = $0.
""",
        encoding="utf-8",
    )
    print(f"[bundle] escrito: {readme.relative_to(ROOT)}")


def make_zip() -> Path:
    plat = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(
        platform.system(), platform.system().lower()
    )
    out = ROOT / "dist" / f"video-gen-pipeline-{plat}-v{VERSION}.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in DIST.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(DIST.parent))
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"[bundle] zip: {out.relative_to(ROOT)} ({size_mb:.1f} MB)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", action="store_true", help="Ademas zipea para GitHub Release.")
    args = parser.parse_args()

    ensure_built()
    copy_workspace()
    write_readme()
    if args.zip:
        make_zip()
    print(f"[bundle] OK. Carpeta lista: {DIST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
