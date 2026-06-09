---
name: narrative-cut
description: Edición autónoma del corte final cuando no hay editora. La IA ve cada plano (Haiku), genera motion graphics (movis) y monta el corte (mcp-video) priorizando el mensaje sobre el pulido.
metadata:
  type: skill
  layer: L10
  decision: D-042
---

# narrative-cut — el corte autónomo (sin editora)

Cierra el bucle de [D-029] (export bundle) cuando **no hay editora humana**. Un
agente (Opus) arma el **corte final** priorizando que **el mensaje llegue por
encima del pulido** ([D-042]). Tres piezas con roles separados:

- **`describe`** = los **ojos** ([D-041]): Claude **Haiku** mira cada plano y dice si
  es **usable**, qué tan **en-mensaje** está y qué problemas tiene.
- **`graphics`** = el **artista** ([D-042]): **movis** genera motion graphics
  deterministas (lower-thirds, placas) por el CLI.
- **mcp-video** = el **ingeniero**: servidor **MCP** con tools guardrailed que el
  agente usa **directo** para el montaje pesado (cortar, ordenar, overlay,
  subtítulos, normalizar, mezclar, checkpoint, export).

## Cuándo usar esto

Ya hay un **render** del proyecto (`pipeline render <slug>` corrido). Si no, corre
[[keyframe-best-of-n]] antes (genera los planos que aquí se montan).

## Qué hace el pipeline (no lo reimplementes)

`export` arma el bundle limpio (`media/`, `frames/`, `rough_cut.mp4`,
`subtitulos.srt`, `guion.md`). `describe` escribe `descriptions.yaml` (evaluación por
plano). `graphics` deja los assets en `export/graphics/`. El **montaje** lo hace el
agente con **mcp-video** (no hay subcomando `edit`: es decisión narrativa, no
determinista — [D-042]).

## Flujo (export → describe → graphics → montar → revisar)

```bash
# 1. Bundle limpio desde el último run
uv run pipeline export <slug>

# 2. Ojos: Haiku evalúa cada plano (usable / en-mensaje / roto)
uv run pipeline describe <slug>     # -> projects/<slug>/descriptions.yaml

# 3. Artista: motion graphics deterministas (requiere extra [edit])
uv run pipeline graphics <slug>     # -> projects/<slug>/export/graphics/
```

4. **(agente, vía mcp-video)** monta el corte **para el mensaje**:
   - lee `descriptions.yaml` y **descarta** los planos `usable: false`;
   - ordena los planos por el `guion.md` (el beat manda, no el orden de archivo);
   - **recorta** lo que sobra (aprieta el ritmo);
   - hace **overlay** de `export/graphics/lt_<base>.png` sobre su plano y mete
     `title.mp4`/`end.mp4` al inicio/cierre;
   - añade subtítulos desde `export/subtitulos.srt` (ya sincronizados);
   - **normaliza** audio y mezcla la música (`export/media/music.*`) por debajo;
   - corre un **release checkpoint** de mcp-video y **exporta** `final_cut.mp4`.

5. **Revisa** `final_cut.mp4`. Itera: `graphics` es determinista (se rehace gratis);
   el corte se rehace con mcp-video sin volver a generar video.

## Cómo llamar a mcp-video

mcp-video trae su **propia skill** (`$mcp-video`) y `docs/TOOLS.md` con las 119
herramientas. No la dupliques: aquí decides **qué** corte hacer (juicio narrativo);
allí está el **cómo** mecánico (trim/merge/overlay/subtítulos/normalize/checkpoint).
Se registra en `.mcp.json` (corre por `uvx`, no es dependencia del proyecto).

## El mensaje importa más que el pulido

No buscamos el montaje de un profesional. Buscamos que **se entienda el mensaje**:
descartar lo roto, ordenar por el guion, subrayar las frases clave con lower-thirds,
y cerrar limpio. Si un plano transmite aunque no sea perfecto, **va**. Si uno es
bonito pero está fuera de mensaje, **fuera**.

## Estado que deja en el proyecto (legible por máquina)

- `projects/<slug>/descriptions.yaml` — evaluación por plano (`usable`, `on_message`,
  `issues`, `description`). Sobrevive a un re-export (vive en la raíz, no en `export/`).
- `projects/<slug>/export/graphics/` — `lt_<base>.png` (lower-thirds con alpha),
  `title.mp4`, `end.mp4`.
- `projects/<slug>/export/final_cut.mp4` — el corte final (lo escribe mcp-video).

## Errores comunes

- `describe`/`graphics` antes de `export` → no hay bundle. Corre `export` primero.
- `graphics` sin el extra → instala con `uv sync --extra edit`.
- `describe` sin `ANTHROPIC_API_KEY` → escribe entradas vacías (`usable: true`): no
  descarta nada (permisivo). Pon la key para tener ojos de verdad.

## Anterior / siguiente

Antes: [[keyframe-best-of-n]] (los planos a montar). Esta skill es el **último** paso:
del bundle al `final_cut.mp4`.

<!-- smoke: invocaciones mínimas que CI verifica (sin llamar a modelos). D-023.
     mcp-video queda fuera del smoke: es un servidor MCP, no un subcomando del CLI. -->
<!-- smoke
pipeline export --help
pipeline describe --help
pipeline graphics --help
-->
