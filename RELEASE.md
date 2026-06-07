# RELEASE.md — cómo bajar y usar el bundle

Este repo distribuye un **bundle ejecutable** para Windows / macOS / Linux
pensado para usuarios no-técnicos. No necesitás Python, ni `uv`, ni
`ffmpeg`: bajás un `.zip`, lo extraés, y doble-click en `pipeline.exe`.

## Para el usuario final (lo que querés pegar en el README de GitHub Releases)

1. Andá a [Releases](../../releases) y bajá el `.zip` de tu plataforma:
   - Windows: `video-gen-pipeline-windows-vX.Y.Z.zip`
   - macOS:   `video-gen-pipeline-macos-vX.Y.Z.zip`
   - Linux:   `video-gen-pipeline-linux-vX.Y.Z.zip`

2. Extraé el `.zip` en cualquier carpeta (Escritorio, Documentos, donde quieras).

3. Copiá `.env.example` a `.env` en la misma carpeta y completá tus API keys
   (al menos `FAL_KEY` y `ANTHROPIC_API_KEY`):
   ```
   FAL_KEY=...
   ANTHROPIC_API_KEY=...
   ```
   Sin esto el binario no puede llamar a las APIs de video.

4. **Doble-click en `pipeline.exe`** (o `pipeline` en macOS/Linux). Se abre
   una ventana con 3 botones:
   - **Renderizar video** — genera el video del proyecto ejemplo `lego_mix/`
   - **Abrir Studio (web)** — abre la UI web local en `http://127.0.0.1:8765`
     para iterar keyframes y caras
   - **Abrir carpeta del proyecto** — abre el explorador de archivos

5. El video final queda en:
   ```
   projects/lego_mix/runs/<run-id>/final_9x16.mp4
   ```
   (lo ves en la misma carpeta que abrió el botón "Abrir carpeta del proyecto")

## Para devs (cómo se construye el bundle)

```bash
# Setup
uv sync --extra apis --extra studio --extra dev
uv pip install pyinstaller

# Build (tarda 2-5 min)
python scripts/build.py --zip

# Resultado:
#   dist/pipeline/                       # carpeta del bundle
#   dist/video-gen-pipeline-<plat>-vX.Y.Z.zip   # listo para GitHub Release
```

## Cómo se taggea un release (flujo del mantenedor)

1. Bump la versión en `pyproject.toml` y `src/pipeline/__init__.py`.
2. Commit + tag:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. GitHub Actions (`.github/workflows/release.yml`) corre el build en matriz
   (windows-latest, macos-latest, ubuntu-latest), sube los 3 zips como assets
   del release automáticamente.

## Estructura del bundle (qué hay en el `.zip`)

```
video-gen-pipeline-windows-v0.1.0.zip
└── pipeline/
    ├── pipeline.exe          # entry (doble-click)
    ├── _internal/            # Python + todas las deps (~200MB)
    │   ├── ffmpeg.EXE        # ← bundleado, no necesita PATH
    │   ├── python311.dll
    │   └── ...
    ├── config/               # providers.yaml, routing.yaml, styles/
    ├── projects/
    │   └── lego_mix/         # proyecto ejemplo (project.yaml, cache pre-llena)
    ├── .env.example          # template de API keys
    └── README.txt            # quick start de 30 segundos
```

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| "Tk no disponible" | Sesión SSH o contenedor sin display | Corré en una sesión con desktop |
| "FAL_KEY not set" | Sin `.env` o sin keys | Copiá `.env.example` a `.env` y completá |
| "ffmpeg no está en el PATH" | Faltaría bundlear | Reportalo (debería estar en `_internal/`) |
| GUI no abre, ventana parpadea | Antivirus bloqueando el .exe | Agregá excepción para `pipeline.exe` |
| El render falla con "no such provider" | Falta provider en `config/providers.yaml` | Editá el YAML y reintentá |

## Límites conocidos

- **Un proyecto por bundle en v1.** El `lego_mix/` viene incluido como
  ejemplo. Para usar otros proyectos, copialos manualmente a `projects/`
  en la carpeta del bundle.
- **Sin auto-update.** Cada release nuevo requiere re-descargar.
- **Sin firma de código en v1.** Windows SmartScreen puede mostrar warning
  la primera vez ("más info → ejecutar de todos modos"). Mac es más estricto
  (Gatekeeper) — hay que `xattr -d com.apple.quarantine pipeline`.
