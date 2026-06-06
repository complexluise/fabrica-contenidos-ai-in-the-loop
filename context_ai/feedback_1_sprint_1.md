# Feedback 1 — Sprint 1 (MVP vertical)

> Evaluación de la implementación del Sprint 1 contra [`SPEC.md`](../SPEC.md) y
> [`ROADMAP.md`](../ROADMAP.md). Tests corridos: **24/24 ✓**.

## Veredicto general

**Coherencia con SPEC: alta.** Las 10 capas existen, los contratos Pydantic son 1:1
con §2, el LoRA vive en L3 (decisión clave de §3), la telemetría es transversal
desde el día 1, y los tests cubren exactamente lo que el ROADMAP marca como 🔬
(router, gate, telemetría, contracts, classifier, config). Los 5 AC del Sprint 1
son alcanzables con el smoke barato.

Commits ordenados por capa (uno lógico por área), estructura de carpetas tal cual
el SPEC §7, separación de I/O externo (Claude, fal) detrás de funciones
aisladas (`_submit_fal`, `parse_judge_response`) → mockeables sin tocar lógica.

---

## Puntos preocupantes (bugs latentes, no decisiones diferidas)

### 1. El Quality Gate VLM no mira el video

**Archivo:** `src/pipeline/gate.py:80-86`

El `messages.create` a Claude manda **sólo el prompt textual** — nunca se sube un
frame del `.mp4` ni del keyframe. Claude está puntuando cuán bonito suena el
prompt, no si el clip respeta nada.

`parse_judge_response` está bien testeado en frío, pero el wrapper online es un
**placebo**. AC3 se cumple formalmente (reintenta), pero la señal que dispara el
reintento es ruido.

**Fix:** extraer 1 frame con ffmpeg del `result.video_path` y mandarlo como
`image` en el message a Claude (que tiene capacidad de visión real).

### 2. Model id de Claude inventado: `claude-opus-4-8`

**Archivos:** `src/pipeline/ingest.py:50`, `src/pipeline/classifier.py:44`,
`src/pipeline/gate.py:81`

Ese ID no existe en la API de Anthropic (los reales son tipo
`claude-opus-4-1-20250805` o `claude-3-5-sonnet-...`). El primer smoke con
`ANTHROPIC_API_KEY` puesto va a 404.

Como hoy se está smokeando con el gate permisivo (sin key), no se notó.

**Fix:** revalidar el catálogo de Anthropic y centralizar el model id en
`settings.py` o en un YAML (no hardcoded en 3 sitios).

### 3. `build_provider` para backend `google` redirige a `FalProvider`

**Archivo:** `src/pipeline/providers/base.py:54-58`

```python
if cfg.backend == "google":
    from .fal_kling import FalProvider
    return FalProvider(cfg)
```

Y el CLI instancia **todos** los providers del YAML (`src/pipeline/cli.py:42`),
incluido `veo`. Hoy zafa porque `smoke.yaml` es 1 escena de volumen que el
router manda a kling; en cuanto una escena exija `needs_audio=true` (como
`briefs/example.yaml:16`), `pick_provider` elige `veo`, se instancia como
FalProvider con `model="veo-3.1"`, y fal explota con un model id que no existe
ahí.

**Fix corto:** `raise NotImplementedError("backend google: Sprint 2")` y filtrar
en `cli.py` a los providers con backend soportado en el sprint actual.

---

## Debilidades menores (radar)

### 4. `concat_clips` usa `-c copy` (stream copy)

**Archivo:** `src/pipeline/assemble.py:36`

Aguanta con un solo provider (Kling, siempre mismo codec/fps/resolución); en
Sprint 2 con clips mezclados de Seedance/Veo va a romper o producir video
silenciosamente roto. Va a haber que re-encodear (`-c:v libx264 -c:a aac`) o
normalizar antes del concat.

### 5. LoRA LEGO es placeholder

**Archivo:** `config/styles/lego.yaml:8` → `lora: "<url-o-id-del-lora-lego>"`

El código lo detecta y lo omite (`src/pipeline/keyframe.py:48`), así que AC4
(*"`--style` altera el look sin tocar código"*) hoy depende **100% de prompt
engineering**, no de LoRA. Es razonable como punto de partida (el SPEC dice
20–50 imgs para entrenarlo) pero conviene no auto-engañarse: el "estilo LEGO"
actual = sufijo en el prompt.

### 6. Paths hardcodeados a `out/...` plano

- `src/pipeline/keyframe.py:27` → `out/keyframes`
- `src/pipeline/providers/fal_kling.py:51` → `out/clips`
- `src/pipeline/telemetry.py:53` → `out/telemetry.sqlite`

Exactamente lo que el **Sprint 1.5** va a arreglar. Si corres dos veces, los
keyframes se sobreescriben por `scene_id`. Confirmado: el problema ya está en
código, no es teórico.

### 7. El `SmartRouter` ignora `cfg.routing.hybrid`

`src/pipeline/cli.py:42` pasa la lista entera de providers al router, sin mirar
qué subset declara `routing.yaml` por clase. Coherente con MVP (sólo existe el
router), pero atado al punto #3: hoy escenas hero/standard/volume todas van por
router contra todos los providers. En Sprint 2 hay que cablear el dispatcher.

### 8. La capability `i2v` nunca se exige

**Archivo:** `src/pipeline/contracts.py:29-42`

`SceneRequirements.required_capabilities()` no incluye `"i2v"`. Si en Sprint 2
entra un provider text-to-video puro, el router lo elegiría también porque
nadie lo descarta. Pequeño hueco semántico — todo el pipeline asume i2v pero no
lo declara como requisito.

### 9. `cost_usd` es estimado, no facturado

`BaseProvider.estimate_cost = cost_per_second * duration_s`
(`src/pipeline/providers/base.py:28-29`). El SPEC ya lo asume, pero vale
tenerlo presente: para validar el "ahorro 60–70%" del §9 va a haber que
cruzarlo con la factura real de fal (Kling cobra por clip de duración
discretizada, no por segundo continuo) y registrar el delta.

### 10. `Telemetry` no se cierra si algo falla

`src/pipeline/cli.py`: si una escena explota a mitad del loop,
`telemetry.close()` no se ejecuta, la DB queda abierta y el `run_report.json`
no se escribe. No es trágico, pero un `try/finally` o convertir `Telemetry` en
context manager (`__enter__/__exit__`) sería más prolijo y consistente con la
idea de "telemetría no opcional".

---

## Cosas menores / estilo

- `tests/test_config.py` está **untracked** en git (no commiteado) aunque ya se
  ejecuta en la suite. Trivial pero llamativo: el commit `419c09d` habla de
  "21 tests" y hoy son 24.
- `Telemetry.totals` cuenta `scenes` con `len(set(scene_id))` (correcto) y
  `attempts` con `len(records)` (correcto). Bien.
- `pyproject.toml` separa `[apis]` y `[dev]` extras — limpio. Permite correr
  tests sin instalar anthropic/fal-client.
- `pydantic-settings` + `.env` + `.env.example` + `.gitignore` con `.env` y
  `out/` → higiene de secretos correcta.

---

## Prioridad de fixes antes de cerrar Sprint 1

1. **Quality Gate con frame real** (#1) — sin esto, AC3 es teatro.
2. **Model id de Claude válido** (#2) — sin esto, ningún path con LLM corre.
3. **`build_provider` no miente con google** (#3) — sin esto, hay crash latente
   en cuanto el brief tenga una escena con audio.

Lo demás (4–10) son deudas conocidas o aceptables como decisiones de MVP. #6
está oficialmente agendado en Sprint 1.5.
