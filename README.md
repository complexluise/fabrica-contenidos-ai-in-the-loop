# Video Gen Pipeline

Industrialización de video con IA: orquestación multi-modelo **API-only** (Kling / Seedance / Veo
vía fal.ai), estilo parametrizable (LEGO por defecto), Quality Gate con Claude visión, caché que
abarata la iteración, y **checkpoints humanos "AI-in-the-Loop"** (eliges la cara del personaje y el
keyframe entre varias opciones).

Docs: [`SPEC.md`](./SPEC.md) (arquitectura y contratos) · [`ROADMAP.md`](./ROADMAP.md) (plan por
sprints) · [`decisions/`](./decisions/) (decisiones ADR, numeradas y con estado).

## Estado actual (Sprints 1–4.6 cerrados)

Funciona end-to-end: definir proyecto → **castear personaje** (N caras, eliges una) → **generar y
elegir keyframes** por escena → **renderizar** el video → ensamblar → entregar 9:16. Caché a nivel
proyecto: re-correr sin cambios cuesta $0. Siguiente: Sprint 5 (música + captions + robustez).

## Requisitos

- **Python 3.12** y **[uv](https://docs.astral.sh/uv/)** (gestión de entorno/deps).
- **ffmpeg** en el `PATH` (ensamblaje, reframe, extracción de frames del gate).

## Instalación

```bash
uv sync --extra apis --extra dev    # core + APIs (anthropic, fal-client) + pytest
# añade --extra vision              # opcional: torch + open_clip (señales CLIP/aesthetic, dormidas)
```

### Variables de entorno (`.env`)

Copia `.env.example` a `.env` y rellena tus claves (las lee `pipeline/settings.py`):

| Var | Para qué | ¿Obligatoria? |
|---|---|---|
| `FAL_KEY` | Keyframe (Flux / nano-banana) y video (Kling/Seedance) vía fal.ai | **Sí** |
| `ANTHROPIC_API_KEY` | Descomposición de guion, clasificador y Quality Gate (Claude visión) | Recomendada |
| `GOOGLE_API_KEY` | Veo (tier hero con audio); adapter aún sin validar contra la API real | Opcional |
| `ELEVENLABS_API_KEY` | Voz en off por escena (TTS); solo si una escena usa `voiceover:` | Opcional |

Sin `ANTHROPIC_API_KEY` el gate es permisivo (no bloquea). El gate además es **suave por defecto**
(`enforce: false` en `routing.yaml`): puntúa y registra pero no regenera mientras iteras.

## Quickstart

Un **proyecto** vive en `projects/<slug>/project.yaml` (ver estructura abajo). Hay dos modos:

### Modo interactivo (AI-in-the-Loop) — recomendado

```bash
# 1) Casting: genera N caras del personaje (combina sus refs + prompt) y abre una hoja de contactos
uv run pipeline cast lego_demo --n 4
uv run pipeline pick-cast lego_demo juan=2        # fija la cara elegida

# 2) Keyframes: genera N encuadres por escena, abre la hoja de contactos
uv run pipeline keyframes lego_demo --n 4
uv run pipeline pick lego_demo s1=0 s2=3          # elige el keyframe de cada escena

# 3) Render: genera el video usando los keyframes elegidos
uv run pipeline render lego_demo
# -> projects/lego_demo/runs/<run_id>/final_9x16.mp4 + run_report.json + manifest.yaml
```

`cast`/`keyframes` escriben una **hoja de contactos HTML** que se auto-abre; eliges por índice
(`escena=N`). Las selecciones se guardan en el proyecto (resumible). Volver a correr lo ya generado
es gratis (caché).

### Modo autónomo (un solo paso)

```bash
uv run pipeline run lego_demo                      # IA elige todo, sin checkpoints
uv run pipeline run --brief briefs/example.yaml    # smoke suelto a out/ (sin proyecto/caché)
```

## `project.yaml`

```yaml
project: lego_demo
style: lego                  # -> config/styles/<style>.yaml (prompt template, ref_model, etc.)
format: "9:16"
music: data/bed.mp3          # música de fondo opcional (ducked si hay voz en off)
voice_id: 21m00Tcm4TlvDq8ikWAM   # voz ElevenLabs por defecto (opcional; multilingüe si se omite)
characters:
  juan:
    design:                  # inputs para 'cast' (diseñar la cara)
      prompt: "hombre con barba como minifigura LEGO"
      refs: [data/juan_persona.jpg, data/lego_style.jpg]   # sujeto + referencia de estilo
    # refs: [...]            # alternativa: cara canónica fija (sin casting)
scenes:
  - id: s1
    prompt: "Plano general de una ciudad LEGO al amanecer"
    duration_s: 5
    class: volume            # hero | standard | volume (si se omite, lo clasifica la IA)
    seed: 0                  # subir el seed = "reroll" (regenera SOLO esta escena)
  - id: s2
    prompt: "Juan camina por el parque, plano medio"
    duration_s: 5
    characters: [juan]       # usa la cara elegida en el casting
    voiceover: "Cada mañana, Juan empieza de nuevo."  # narración TTS; la caption se autocompleta de aquí
    # voice_id: <otra-voz>   # override de la voz solo para esta escena
```

> Captions: una escena con `voiceover:` y sin `caption:` **autocompleta** el texto en pantalla
> con el de la voz en off (sin whisper). La música de fondo baja automáticamente (ducking) cuando
> hay narración. Si falta `ELEVENLABS_API_KEY` o la cuenta no tiene crédito, la VO se omite y el
> video sale como en Sprint 5 (música + caption escrita) — no aborta.

Routing (qué estrategia/modelo por clase de escena) y umbrales del gate viven en
`config/routing.yaml`; los modelos y costos en `config/providers.yaml`.

## Tests

```bash
uv run pytest                # core crítico: contracts, routing, gate, telemetría, proyecto/caché, studio
```

Metodología: **TDD test-first**, solo el core crítico. Las APIs externas, ffmpeg y prompts se
validan con smoke run, no con unit tests. (Ver decisiones [D-012], [D-017].)

## Arquitectura

10 capas desacopladas por contratos (L0 Contracts … L9 Telemetría) + modo interactivo de
checkpoints. Detalle, contratos y diagramas en [`SPEC.md`](./SPEC.md); el *por qué* de cada
elección en [`decisions/`](./decisions/).

```
L1 Ingest → L2 Classifier → L3 Keyframe → L4 Providers → L5 Orchestrator (router/cascade/ensemble)
→ L6 Quality Gate (Claude visión) → L7 Assembly → L8 Delivery        (L9 Telemetría transversal)
        ▲ checkpoints humanos: cast / pick-cast (personaje) · keyframes / pick (encuadre)
```
