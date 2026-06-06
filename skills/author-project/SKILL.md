---
name: author-project
description: Convierte un brief/guion en un projects/<slug>/project.yaml válido (escenas + personajes) listo para el pipeline.
metadata:
  type: skill
  layer: L1
  decision: D-023
---

# author-project — del brief al `project.yaml`

**Checkpoint humano #1+#2 de [D-021]** (guion + shot list). La IA descompone y
propone; el humano edita y aprueba. La salida es el **spec declarativo** que el
resto del pipeline consume ([SPEC §7.1](../../SPEC.md)).

## Cuándo usar esto

El usuario tiene una idea, un brief o un guion y quiere arrancar un proyecto de
video. Aún no hay `projects/<slug>/project.yaml`.

## Qué hace el pipeline (no lo reimplementes)

El proyecto **ES** su `project.yaml` versionado en git; el pipeline es una función
pura del spec. Tu trabajo es **escribir ese YAML**, no generar nada todavía.

## Receta

1. **Elige un `slug`** kebab-case estable (p.ej. `spot-agua`). El proyecto vive
   en `projects/<slug>/project.yaml`.
2. **Descompón el guion en escenas.** Cada escena es una toma corta (≈5 s). Por
   escena rellena:
   - `id` — corto y estable (`s1`, `s2`, …). No lo cambies una vez referenciado.
   - `prompt` — qué se ve, en una frase (plano + sujeto + acción + luz).
   - `duration_s` — segundos (≈5 por defecto).
   - `class` — `hero` | `standard` | `volume` (opcional; el clasificador la infiere
     si falta). Sube a `hero` solo las tomas marca.
   - `characters` — lista de nombres del banco que aparecen (consistencia).
   - `seed` — `0` por defecto. **Subirlo es un reroll** de esa escena (nueva
     variante, [SPEC §7.2](../../SPEC.md)).
3. **Declara el banco de personajes** (opcional) en `characters:`. Si una cara hay
   que **diseñarla**, dale un bloque `design:` y luego usa la skill
   [[bank-casting]]. Si ya tienes una imagen canónica, ponla en `refs:`.
4. **Música** (opcional): `music: data/track.mp3`.
5. **Valida**: `uv run pipeline run <slug>` arranca el modo autónomo con caché. Para
   el flujo por etapas (recomendado para video posteable) sigue
   [[bank-casting]] → [[keyframe-best-of-n]].

## Esqueleto de `project.yaml`

```yaml
project: spot-agua             # = slug
style: lego                    # config/styles/<style>.yaml
format: "9:16"                 # 9:16 | 1:1 | 16:9
# music: data/fondo.mp3        # opcional
characters:                    # opcional — banco para consistencia
  mascota:
    design:                    # cara a DISEÑAR -> ver skill bank-casting
      prompt: "personaje convertido en minifigura LEGO, cuerpo de minifigura"
      refs: [data/sujeto.jpeg, data/lego_ref.jpg]   # sujeto + referencia de estilo
scenes:
  - id: s1
    prompt: "Plano general de una ciudad LEGO al amanecer, calles vacías"
    duration_s: 5
    class: standard
    seed: 0
  - id: s2
    prompt: "La mascota LEGO juega en un parque al atardecer, plano medio"
    duration_s: 5
    characters: [mascota]
    seed: 0
```

## Errores comunes

- `project.yaml` **sin `scenes:`** → el loader falla (`load_project_spec`).
- Cambiar un `id` ya referenciado = ruptura. Para una variante, **sube el `seed`**,
  no renombres.
- Hex/colores y detalles de estilo **no van aquí**: viven en
  `config/styles/<style>.yaml`. El `prompt` de escena describe el contenido, no el look.

## Siguiente paso

Si hay personajes con `design:` → [[bank-casting]]. Si no → [[keyframe-best-of-n]].

<!-- smoke: invocaciones mínimas que CI verifica (sin llamar a modelos). D-023. -->
<!-- smoke
pipeline --help
pipeline run --help
-->
