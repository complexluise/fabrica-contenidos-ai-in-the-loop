# Fábrica de contenidos · IA con la persona dentro

> **Convierte un guion en un video vertical 9:16 — donde la IA propone y tú decides.**

[![Licencia: GPL-3.0](https://img.shields.io/badge/Licencia-GPL--3.0-blue.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Gestionado con uv](https://img.shields.io/badge/gestionado%20con-uv-purple.svg)](https://docs.astral.sh/uv/)
[![Estado: en desarrollo activo](https://img.shields.io/badge/estado-en%20desarrollo-success.svg)](./ROADMAP.md)

Un taller para producir video con IA **rápido y consistente, sin perder el control humano**.
Orquesta varios modelos (Kling / Seedance / Veo para video, Flux / nano-banana para imágenes)
a través de [fal.ai](https://fal.ai), pero en cada paso importante **una persona elige entre
varias opciones**: la cara del personaje y el encuadre de cada escena. La IA hace el trabajo
pesado; tú firmas el resultado.

> ### 🤝 Filosofía: tecnologías mixtas
> La IA **propone**; la persona **decide**. La IA es solo *una* herramienta — junto a la oralidad,
> el trabajo en equipo y el oficio. Antes que nada, lee [**FILOSOFIA.md**](./FILOSOFIA.md): es el
> alma del proyecto, no un adorno.

<!-- TODO(demo): agregar aquí un GIF del flujo (hoja de contactos -> elección -> video final).
     Es una herramienta visual; un GIF vale más que tres párrafos. -->

---

## Tabla de contenidos

- [¿Qué obtienes?](#qué-obtienes)
- [Empieza en 5 minutos](#empieza-en-5-minutos)
- [El flujo recomendado: AI-in-the-Loop](#el-flujo-recomendado-ai-in-the-loop)
- [Anatomía de un proyecto (`project.yaml`)](#anatomía-de-un-proyecto-projectyaml)
- [Cómo funciona por dentro](#cómo-funciona-por-dentro)
- [Estado del proyecto](#estado-del-proyecto)
- [Problemas comunes](#problemas-comunes)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

---

## ¿Qué obtienes?

Le das un **guion** (o escenas sueltas) y obtienes un **video vertical 9:16** listo para
publicar — o, mejor, un **paquete de edición** ordenado para que una persona dé el corte final.
Por el camino:

- **Eliges la cara** del personaje entre N candidatas (*casting*) y el **encuadre** de cada
  escena entre N keyframes. La IA genera; tú decides.
- **Caché que abarata iterar:** re-correr lo ya generado cuesta **$0**. Subir un `seed` regenera
  *solo* esa escena ("reroll").
- **Un asistente de calidad** (Claude visión) que *ordena* los candidatos para que elijas más
  rápido — nunca decide solo.
- Voz en off por escena (TTS), música de fondo con *ducking* y subtítulos automáticos.

> 💳 **Esto usa APIs de pago.** Vas a necesitar al menos una `FAL_KEY` con crédito para generar.
> El resto de las claves son opcionales (ver tabla abajo). Sin claves, los tests corren igual,
> pero no se genera media real.

## Empieza en 5 minutos

### 1. Requisitos

- **Python 3.12** y **[uv](https://docs.astral.sh/uv/)** (gestiona entorno y dependencias).
- **ffmpeg** en el `PATH` (ensamblaje, reframe, extracción de frames).

### 2. Instala

```bash
git clone https://github.com/complexluise/fabrica-contenidos-ai-in-the-loop.git
cd fabrica-contenidos-ai-in-the-loop
uv sync --extra apis --extra dev      # core + APIs (anthropic, fal-client) + pytest
```

### 3. Pon tus claves

```bash
cp .env.example .env                   # y rellena FAL_KEY (las lee src/pipeline/settings.py)
```

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `FAL_KEY` | Keyframes (Flux / nano-banana) y video (Kling / Seedance) vía fal.ai | **Sí** |
| `ANTHROPIC_API_KEY` | Descomposición de guion, clasificador y Quality Gate (Claude visión) | Recomendada |
| `GOOGLE_API_KEY` | Veo (tier hero con audio); adapter aún sin validar contra la API real | Opcional |
| `ELEVENLABS_API_KEY` | Voz en off por escena (TTS); solo si una escena usa `voiceover:` | Opcional |

Sin `ANTHROPIC_API_KEY` el gate es **permisivo** (no bloquea). Además es **suave por defecto**
(`enforce: false` en `config/routing.yaml`): puntúa y registra, pero no regenera mientras iteras.

### 4. Tu primer video (hola mundo)

El repo ya incluye un proyecto de ejemplo, **`projects/lego_demo`** (una escena, sin personajes).
Solo necesita `FAL_KEY`:

```bash
uv run pipeline run lego_demo
# -> projects/lego_demo/runs/<run_id>/final_9x16.mp4
# Re-correrlo sin cambios cuesta $0 (caché). Subir el `seed` de la escena la regenera.
```

> 👀 ¿Quieres ver el resultado **antes** de gastar un peso? Este ejemplo viene versionado en
> [`projects/lego_demo/`](./projects/lego_demo/): la entrada, el keyframe elegido y el
> [video final](./projects/lego_demo/final_9x16.mp4) ya están en el repo.

¿Prefieres probar sin tocar un proyecto? Hay un brief suelto que va a `out/`:

```bash
uv run pipeline run --brief briefs/example.yaml
```

¿Funcionó? Genial. Ahora pasemos al flujo donde **tú** tomas las decisiones.

## El flujo recomendado: AI-in-the-Loop

Aquí está lo que hace especial a este proyecto: un flujo **por etapas, reanudable**, donde la
persona elige en cada checkpoint. Como generar es lento (keyframe ~30-60s, video 1-3 min) y
re-correr lo ya hecho es gratis, puedes parar y retomar cuando quieras.

### Encuadre y render (sobre el ejemplo incluido)

Con el `lego_demo` que ya viene en el repo puedes ejercer los checkpoints de **keyframe**:

```bash
# Keyframes: genera N encuadres de la escena y abre una hoja de contactos HTML
uv run pipeline keyframes lego_demo --n 4
uv run pipeline pick lego_demo s1=0               # eliges el keyframe (por índice) de la escena s1

# Render: arma el video usando el keyframe elegido
uv run pipeline render lego_demo
# -> projects/lego_demo/runs/<run_id>/final_9x16.mp4 + run_report.json + manifest.yaml
```

`keyframes` abre una **hoja de contactos HTML** automáticamente; eliges por índice (`escena=N`).
Las selecciones se guardan en el proyecto, así que el flujo es **reanudable**.

### Casting de personaje (cuando tu proyecto tiene un personaje)

El **casting** diseña la cara de un personaje combinando tus **imágenes de referencia** + un prompt,
y te da N opciones para que elijas. Para usarlo, tu `project.yaml` debe declarar un personaje con
sus refs (las imágenes van en `data/`, que está gitignored — pon las tuyas):

```yaml
characters:
  juan:
    design:
      prompt: "hombre con barba como minifigura LEGO"
      refs: [data/juan.jpg, data/lego_style.jpg]   # sujeto + referencia de estilo
```

```bash
uv run pipeline cast lego_demo --n 4
uv run pipeline pick-cast lego_demo juan=2         # fija la cara; luego keyframes/pick/render la usan
```

La estructura completa de un proyecto (voz en off, música, seeds, planos) está
[más abajo](#anatomía-de-un-proyecto-projectyaml).

### ¿Prefieres una interfaz gráfica?

```bash
uv run pipeline studio                 # app web local en http://127.0.0.1:8765
```

### ¿Quieres entregar a una editora?

```bash
uv run pipeline export lego_demo       # arma media/ + frames/ + guion + subtítulos en un solo paquete
```

### Modo autónomo (la IA decide todo)

```bash
uv run pipeline run lego_demo          # un solo paso, sin checkpoints humanos
```

## Anatomía de un proyecto (`project.yaml`)

<details>
<summary>Ver el <code>project.yaml</code> completo con todas las opciones</summary>

```yaml
project: lego_demo
style: lego                  # -> config/styles/<style>.yaml (prompt template, ref_model, etc.)
format: "9:16"
music: data/bed.mp3          # música de fondo opcional (baja de volumen si hay voz en off)
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

**Captions:** una escena con `voiceover:` y sin `caption:` **autocompleta** el texto en pantalla
con el de la voz en off (sin whisper). La música baja automáticamente (*ducking*) cuando hay
narración. Si falta `ELEVENLABS_API_KEY` o no hay crédito, la voz se omite y el video sale con
música + caption escrita — **no aborta**.

</details>

El *routing* (qué estrategia y modelo por clase de escena) y los umbrales del gate viven en
`config/routing.yaml`; los modelos y costos por segundo, en `config/providers.yaml`.

## Cómo funciona por dentro

10 capas desacopladas por contratos (`L0 Contracts … L9 Telemetría`) más el modo interactivo de
checkpoints. El detalle, los contratos y los diagramas están en [`SPEC.md`](./SPEC.md); el *por
qué* de cada elección, en [`decisions/`](./decisions/) (ADR numerados).

```
L1 Ingest -> L2 Classifier -> L3 Keyframe -> L4 Providers -> L5 Orchestrator (router/cascade/ensemble)
-> L6 Quality Gate (Claude visión) -> L7 Assembly -> L8 Delivery        (L9 Telemetría transversal)
        ^ checkpoints humanos: cast / pick-cast (personaje) · keyframes / pick (encuadre)
```

**Tests:**

```bash
uv run pytest                # core crítico: contracts, routing, gate, telemetría, proyecto/caché, studio
```

Metodología: **TDD test-first, solo del core crítico**. Las APIs externas, ffmpeg y prompts se
validan con *smoke runs* reales, no con unit tests (ver [`CONTRIBUTING.md`](./CONTRIBUTING.md)).

## Estado del proyecto

Funciona **de extremo a extremo**: definir proyecto → castear personaje → generar y elegir
keyframes → renderizar → ensamblar → entregar 9:16, con voz en off, música y subtítulos.

| Capacidad | Estado |
|---|---|
| Flujo interactivo (cast / keyframes / render) | ✅ Funciona |
| Caché content-addressed (re-correr = $0) | ✅ Funciona |
| Quality Gate con Claude visión (asistente) | ✅ Funciona |
| Voz en off (TTS), música con ducking, subtítulos | ✅ Funciona |
| App web local (`studio`) y paquete de edición (`export`) | ✅ Funciona |
| Comando para crear un proyecto (`init`) | 🔜 Falta (hoy partes del ejemplo `lego_demo` o lo creas a mano) |
| Veo (Google) validado contra la API real | 🔜 Pendiente |

El plan detallado por hitos está en [`ROADMAP.md`](./ROADMAP.md).

## Problemas comunes

| Síntoma | Causa probable / solución |
|---|---|
| `ffmpeg not found` | ffmpeg no está en el `PATH`. Instálalo y reabre la terminal. |
| El comando `cast`/`keyframes` falla con "proyecto no encontrado" | No existe `projects/<slug>/project.yaml`. Usa el ejemplo `lego_demo` o crea el tuyo (ver [anatomía](#anatomía-de-un-proyecto-projectyaml)). |
| No se genera media / error de autenticación | Falta `FAL_KEY` en `.env` o la cuenta no tiene crédito. |
| El gate "no hace nada" | Es **suave por defecto** (`enforce: false`) y permisivo sin `ANTHROPIC_API_KEY`. Es esperado. |
| Caracteres raros / crash en consola (Windows) | El host es cp1252; reporta el caso. La salida del pipeline evita no-ASCII a propósito. |

## Contribuir

Los aportes son bienvenidos — y aquí se aprende preguntando. Empieza por:

1. [`FILOSOFIA.md`](./FILOSOFIA.md) — el espíritu (un buen aporte mantiene a la persona en el centro).
2. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — setup con `uv`, tests, flujo de PR y checklist.
3. [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — convivencia basada en respeto y cuidado.

¿Idea o bug? Abre un [issue](../../issues/new/choose). ¿Una duda? Abre una discusión.
**Nunca** subas claves ni un `.env` (revisa tu diff antes del PR).

## Licencia

[GPL-3.0-only](./LICENSE). Puedes usar, estudiar, modificar y compartir este software; si lo
distribuyes (modificado o no), debe seguir siendo libre bajo la misma licencia.
