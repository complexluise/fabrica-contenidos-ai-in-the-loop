---
name: bank-casting
description: Diseña la cara canónica de un personaje (best-of-N a partir de imágenes + prompt) y fija la elegida para propagar identidad entre tomas.
metadata:
  type: skill
  layer: L3
  decision: D-023
---

# bank-casting — casting + look-dev del personaje

**Checkpoint humano #3 de [D-021]** (casting/look-dev): *la base de toda la
consistencia, todo lo hereda*. La IA genera **N caras candidatas**; el humano elige
una. La elegida se vuelve la referencia canónica que heredan todas las escenas con
ese personaje.

## Cuándo usar esto

El `project.yaml` tiene uno o más `characters:` con un bloque `design:` (una cara a
diseñar, no una imagen ya fija). Hazlo **antes** de [[keyframe-best-of-n]] para que
los keyframes hereden la cara correcta.

## Qué hace el pipeline (no lo reimplementes)

`cast` genera N variantes combinando las `design.refs` (sujeto + referencia de
estilo) con `design.prompt`, las cachea por hash y abre una **hoja de contactos
HTML** ([D-022]). `pick-cast` persiste la elección en `casting.yaml`, que el runner
aplica como `refs` canónica del personaje.

## Flujo (dispara → revisa → elige)

```bash
# 1. Genera N caras candidatas por personaje con design: y abre la hoja de contactos
uv run pipeline cast <slug> --n 4

# 2. (humano) mira projects/<slug>/cast_review.html y anota el índice por personaje

# 3. Fija la cara elegida (personaje=índice, base 0)
uv run pipeline pick-cast <slug> mascota=2
```

### Atajo: ya tengo la cara ([D-025])

Si la cara **ya existe** (de afuera o decidida), tómala directo sin `cast`/candidatos:

```bash
uv run pipeline pick-cast <slug> --face mascota=ruta/cara.png
```

Escribe la misma `casting.yaml` que el flujo de candidatos; falla si la ruta no existe.

- La generación es **no bloqueante**: la hoja de contactos al abrirse es la señal de
  "listo" ([D-022]).
- Candidatos cacheados por hash ([D-013]): re-correr `cast` sin cambios cuesta $0.
- Elige **un índice por personaje**; puedes fijar varios de una:
  `pipeline pick-cast <slug> mascota=2 villano=0`.

## Estado que deja en el proyecto (legible por máquina)

- `projects/<slug>/cast_candidates.yaml` — los N candidatos por personaje.
- `projects/<slug>/casting.yaml` — la elección canónica (lo que el runner lee).
- `projects/<slug>/cast_review.html` — la hoja de contactos.

## Errores comunes

- `cast` sin ningún `design:` en `project.yaml` → `RuntimeError`. Añade el bloque
  `design:` (ver [[author-project]]) o usa `refs:` directo si ya tienes la cara.
- `pick-cast` antes de `cast` → no hay candidatos. Corre `cast` primero.
- Índice fuera de rango (0..N-1) → error con el rango válido.

## Siguiente paso

Con la cara fijada → [[keyframe-best-of-n]] (los keyframes heredan la cara elegida).

<!-- smoke: invocaciones mínimas que CI verifica (sin llamar a modelos). D-023. -->
<!-- smoke
pipeline cast --help
pipeline pick-cast --help
-->
