---
name: keyframe-best-of-n
description: Genera N keyframes por escena, deja que el humano elija el mejor por escena, y renderiza el video con los elegidos.
metadata:
  type: skill
  layer: L3
  decision: D-023
---

# keyframe-best-of-n — el checkpoint del keyframe

**Checkpoint humano #4 de [D-021]** (keyframe best-of-N): el corazón del flujo
AI-in-the-Loop. La IA genera **N candidatos por escena** y el Gate los **ordena**
(mejor primero, [D-021]); el humano elige uno por escena; el render hereda esos
keyframes elegidos como `init_image` de los modelos image-to-video ([SPEC §0](../../SPEC.md)).

## Cuándo usar esto

Ya existe `projects/<slug>/project.yaml` con escenas. Si hay personajes a diseñar,
corre [[bank-casting]] **antes** (los keyframes heredan la cara elegida).

## Qué hace el pipeline (no lo reimplementes)

`keyframes` genera N candidatos/escena (seed distinto por candidato), los cachea por
hash y abre la **hoja de contactos**. `pick` valida y persiste la elección en
`selections.yaml` (resumible). `render` exige una selección por escena y genera el
video reusando esos keyframes.

## Flujo (dispara → me voy → vuelvo → elijo → renderizo)

```bash
# 1. Genera N keyframes por escena y abre la hoja de contactos
uv run pipeline keyframes <slug> --n 4

# 2. (humano) mira projects/<slug>/keyframes_review.html y anota el índice por escena

# 3. Registra el keyframe elegido por escena (escena=índice, base 0). Resumible:
#    puedes elegir unas escenas ahora y el resto luego.
uv run pipeline pick <slug> s1=2 s2=0 s3=1

# 3.5 (opcional, recomendado) El film entero en poses ANTES de pagar video (D-060/D-070)
uv run pipeline animatic <slug>

# 4. Renderiza el video con los keyframes elegidos. El elegido ES el frame-0 del
#    clip ("la cámara actúa", D-070); los planos `lands: true` interpolan hacia él.
uv run pipeline render <slug>
```

## Atajo: ya tengo el keyframe ([D-025])

Si **ya tienes la imagen** (de afuera, de una corrida previa, o ya decidida), no hay nada que
elegir: **tómala directo**, salteándote `keyframes`/`pick`.

```bash
uv run pipeline render <slug> --keyframe s1=ruta/imagen.png --keyframe s2=otra.png
```

El flag **gana** sobre `selections.yaml` para esa escena; el resto de escenas sigue usando la
selección persistida. Es flag (no carpeta-convención) porque los artefactos son de tipos distintos
(keyframe / cara de personaje) y el flag hace explícito **qué tipo** inyectas. Si una ruta no
existe, falla con un error que la nombra.

- Generación **no bloqueante**; la hoja de contactos al abrirse = "listo" ([D-022]).
- Candidatos cacheados por hash ([D-013]): re-correr `keyframes` sin cambios = $0.
- `pick` es **resumible**: acumula selecciones entre invocaciones; no hace falta
  elegir todas las escenas de una vez.
- Los `id` de escena salen de `project.yaml` (léelo para saber qué escena=índice fijar).

## Asimetría keyframe ≠ video ([D-022])

Keyframe = **best-of-N + el humano elige** (imágenes, fácil de ver en grid). El
**video** no es best-of-N completo: la IA elige el mejor (Ensemble + gate-ranking) y
el humano vetea/rerollea, porque revisar N videos es caro.

## Estado que deja en el proyecto (legible por máquina)

- `projects/<slug>/candidates.yaml` — los N keyframes por escena (rutas del **caché por hash**, estables).
- `projects/<slug>/selections.yaml` — la elección humana por escena (lo que `render` lee).
- `projects/<slug>/keyframes_review.html` — la hoja de contactos.
- `projects/<slug>/keyframes/` — **alias legibles** (`<escena>_<slug>_<idx>.png`, [D-026]): copias
  con nombre humano del artefacto cacheado por hash. Son las que abres a mano y pasas a `--keyframe`.

## Errores comunes

- `pick` antes de `keyframes` → no hay candidatos. Corre `keyframes` primero.
- `render` con escenas sin elegir → `RuntimeError` listando las que faltan. Completa
  con `pick`.
- Índice fuera de rango (0..N-1) → error con el rango válido.
- Para otra variante de una escena, sube su `seed` en `project.yaml` (reroll) y
  vuelve a correr `keyframes`.

## Anterior / siguiente

Antes: [[author-project]] (y [[bank-casting]] si hay caras a diseñar). Después de
`render`: corte/post (L7).

<!-- smoke: invocaciones mínimas que CI verifica (sin llamar a modelos). D-023. -->
<!-- smoke
pipeline keyframes --help
pipeline pick --help
pipeline render --help
-->
