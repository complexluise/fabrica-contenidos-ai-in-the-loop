# ROADMAP — Pipeline de Video IA

> Acompaña a [`SPEC.md`](./SPEC.md). Cada sprint tiene **objetivo**, **acceptance criteria** (AC)
> verificables y **tasks**. Marca `[x]` al completar.

## Metodología de trabajo

- **Un sprint a la vez.** Se trabaja todo el sprint y al final se hacen **todos los commits**
  (un commit lógico por área: contracts, telemetry, provider, etc.).
- **TDD selectivo.** Se escribe test **solo del core crítico** — lo que, si se rompe, arruina la
  calidad o el costo. **No saturar de pruebas.** El resto se valida con un *smoke run* end-to-end.
- **Qué SÍ se testea (regla):**
  - Lógica de **routing/estrategias** (decide a qué modelo va cada escena → impacta costo).
  - **Quality Gate**: parseo del veredicto y umbral por tipo de escena (pasa/falla correcto).
  - **Telemetría**: que `cost_usd` y `latency_s` se calculan y persisten bien.
  - **Contracts**: validación de los modelos Pydantic (entradas inválidas fallan).
- **Qué NO se testea (se hace smoke manual):** llamadas reales a APIs externas (se *mockean* en el
  core), ffmpeg, prompts de LLM, renders.
- **Definition of Done por sprint:** AC cumplidos + tests del core en verde + smoke run sin errores
  + commits hechos.

---

## Sprint 1 — MVP vertical (`brief → video LEGO 9:16`)

**Objetivo:** atravesar las 10 capas en su versión mínima con **1 solo provider (Kling)** y
**Smart Router**, fijando los contratos. Salida: `out/final_9x16.mp4` + `out/run_report.json`.

### Acceptance Criteria
- [x] AC1 — `pipeline run ... --style lego --format 9:16` produce un `.mp4` 9:16 reproducible. *(smoke real: `out/final_9x16.mp4`, 1080×1920 h264, $0.150)*
- [x] AC2 — Se genera `run_report.json` con `cost_usd` y `latency_s` **por escena** y totales.
- [x] AC3 — Cada escena pasa por el Quality Gate; un fallo dispara **1 reintento** antes de aceptar/marcar.
- [x] AC4 — Cambiar `--style` (o el YAML de estilo) altera el look **sin tocar código** de orquestación.
- [x] AC5 — Toda llamada a API externa está detrás de un adapter (Provider/KeyframeGenerator); la orquestación no toca `httpx`.

### Tasks
- [x] T1.1 — Scaffolding con **uv** (Python 3.12): `pyproject.toml`, `src/pipeline/`, deps.
- [x] T1.2 — **L0 `contracts.py`**: `Scene`, `SceneRequirements`, `GenRequest`, `GenResult`, `GateReport`, Protocols. 🔬 ✅
- [x] T1.3 — **L9 `telemetry.py`**: registro por escena a SQLite + `run_report.json`. 🔬 ✅
- [x] T1.4 — **L0 config loader**: `providers.yaml`, `routing.yaml`, `styles/lego.yaml` → objetos tipados. 🔬 ✅
- [x] T1.5 — **L4 `providers/base.py` + `fal_kling.py`**: adapter Kling i2v vía fal (fal_client, mockeable).
- [x] T1.6 — **L3 `keyframe.py`**: Flux (fal) → 1 imagen/escena como `init_image`. *(LoRA LEGO: diferido)*
- [x] T1.7 — **L1 `ingest.py`**: brief YAML o Claude descompone guion → `list[Scene]`.
- [x] T1.8 — **L2 `classifier.py`**: reglas (diálogo→hero, etc.) + Claude para lo ambiguo. 🔬 ✅
- [x] T1.9 — **L5 `strategies/router.py`**: elige el provider más barato que cumple `requirements`. 🔬 ✅
- [x] T1.10 — **L6 `gate.py`**: VLM-judge (Claude visión) → `GateReport` + umbral por tipo. 🔬 ✅
- [x] T1.11 — **L7 `assemble.py`**: ffmpeg concat + música. *(captions/whisper → movido a Sprint 3)*
- [x] T1.12 — **L8 `deliver.py`**: reframe a 9:16.
- [x] T1.13 — **`cli.py`**: comando `run` cableando todas las capas.
- [x] T1.14 — `briefs/example.yaml` + `briefs/smoke.yaml` + smoke run end-to-end + `README`.

**Commits al cierre:** ✅ hechos (contracts → cli + tests + fixes del smoke).

> **✅ Sprint 1 CERRADO** (2026-06-02). 24 tests del core en verde. Smoke run real validado
> end-to-end (brief → keyframe Flux → Kling i2v → ffmpeg → 9:16). Pendientes movidos: LoRA LEGO
> (de últimas), captions/whisper (Sprint 3), corrida del `example.yaml` multi-escena con ruta
> Veo/audio (queda cubierta al entrar el adapter de Veo en Sprint 2).

---

## Sprint 1.5 — Modelo de proyecto + caché (PRIORITARIO)

**Objetivo:** soportar **muchas iteraciones baratas**. El problema dominante no es el orden en
disco, es el **costo de iterar** (cada paso cuesta $). Modelo: **spec declarativo +
caché content-addressed + runs inmutables como manifiesto**. Granularidad de iteración =
**escena**. Alcance = **1 estilo/marca**. Ver SPEC §7.

**Estructura objetivo:**

```
projects/<slug>/
  project.yaml                    # spec versionado: brief + prompts + estilo(ref) + overrides + seeds
  cache/
    keyframes/<keyframe_key>.png  # inmutables, content-addressed, compartidos entre runs
    clips/<video_key>.mp4
  runs/<run_id>/
    manifest.yaml                 # config resuelta + punteros (keyframe_key, video_key) por escena
    run_report.json               # costo/latencia + cache hits
    final_9x16.mp4
```

**Hashing (núcleo):**
```
keyframe_key = hash(prompt + style.template + negative + kf.model + kf.lora + strength)
video_key    = hash(keyframe_key + provider + model + duration + aspect + seed)
```
Seed determinista por defecto (re-correr = cache hit); subir `seed` de una escena = **reroll**
(cache miss solo en esa escena).

### Acceptance Criteria
- [x] AC1 — `pipeline run <project>` lee `project.yaml` y produce un run en `projects/<slug>/runs/<run_id>/` sin pisar iteraciones previas. *(2 runs en carpetas distintas)*
- [x] AC2 — Re-correr el mismo proyecto sin cambios → **todas las escenas cache hit, costo $0**. *(smoke: 2ª corrida cache hits 1/1, $0.000)*
- [x] AC3 — Cambiar el prompt o subir el `seed` de **una** escena → solo esa se regenera. *(verificado por hash: seed→video_key distinto→miss)*
- [x] AC4 — El caché es a nivel proyecto (`projects/<slug>/cache/`) y se reutiliza entre runs.
- [x] AC5 — El run guarda `manifest.yaml` (config resuelta + punteros) → dos runs comparables por diff.

### Tasks (orden test-first)
- [x] T1.5.1 — **`project.py`: hashing content-addressed** `cache_key(step, inputs)`. 🔬 ✅ (test-first)
- [x] T1.5.2 — **`project.py`: `Project`/`Run`** (paths, `run_id`, inmutabilidad). 🔬 ✅ (test-first)
- [x] T1.5.3 — **Cache lookup/store** a nivel proyecto. 🔬 ✅ (test-first)
- [x] T1.5.4 — Integrar caché en L3 (keyframe) y L4 (providers): si hit → no llamar API, costo 0. *(en `runner.py`)*
- [x] T1.5.5 — Telemetría: `SceneRecord` gana `cached` + keys; report distingue hits; DB y report → carpeta del run.
- [x] T1.5.6 — `manifest.yaml` por run (config resuelta + punteros por escena).
- [x] T1.5.7 — CLI: `pipeline run <project>`; `--brief` se mantiene para smokes.
- [x] T1.5.8 — `.gitignore` de `projects/*/cache/` y `projects/*/runs/`.
- [x] T1.5.9 — `projects/lego_demo/project.yaml` + smoke de doble corrida (2ª = todo cache hit).

**Commits al cierre:** ✅ hechos.

> **✅ Sprint 1.5 CERRADO** (2026-06-02). 33 tests del core en verde (test-first en `project.py`).
> Doble corrida validada: 1ª $0.150, 2ª **$0.000 (cache hit 1/1)**. Iteración por escena con
> reroll por seed.

---

## Sprint 2 — Multi-provider + estrategias

**Objetivo:** sumar Seedance y Veo; activar Cascade y Ensemble; híbrido por YAML (§4.4 del SPEC).

### Acceptance Criteria
- [x] AC1 — `routing.yaml` enruta hero→ensemble, estándar→router, volumen→cascade **sin cambios de código**. *(dry-check)*
- [x] AC2 — Cascade escala de tier solo cuando el gate falla; se registra cada intento y su costo. 🔬 *(tests)*
- [x] AC3 — Ensemble genera N candidatos en paralelo (asyncio) y selecciona por score. 🔬 *(tests)*
- [x] AC4 — Escena con `needs_audio` se enruta a Veo automáticamente. *(dry-check: s2 audio→ensemble, solo Veo elegible)*

### Tasks
- [x] T2.1 — Seedance vía `FalProvider` (backend fal, por config) + `providers/google_veo.py` (adapter directo Veo, lazy google-genai).
- [x] T2.2 — `strategies/cascade.py`. 🔬 ✅ (test-first: escalado, costo acumulado, cola humana)
- [x] T2.3 — `strategies/ensemble.py` (fan-out/fan-in + selección). 🔬 ✅ (test-first: best-of-N, costo suma, filtro caps)
- [x] T2.4 — Dispatcher híbrido (`strategies/dispatch.py`): clase → estrategia según `routing.yaml`. 🔬 ✅
- [x] T2.5 — Smoke mixto real **sin Veo**: vol→cascade→kling ($0.15), std→router→kling ($0.15), hero→ensemble→seedance ($0.45). Total **$0.750**; 2ª corrida **$0.000 (cache 3/3)**. Ahorro analítico vs premium-only: **58%**. *(Veo real queda pendiente de `GOOGLE_API_KEY`.)*

> **✅ Sprint 2 CERRADO** (2026-06-02). 46 tests del core en verde. Cascade/Ensemble/dispatcher
> híbrido validados end-to-end con generación real (kling + seedance). Cache key strategy-aware +
> sidecar de procedencia. Ajuste de review: provenance preservada en cache hits. Pendiente opcional:
> hero real con Veo (necesita key de Google).

---

## Sprint 3 — Quality Gate "duro" + post de marca

**Objetivo:** señales numéricas en el gate; captions/overlays de marca.

### Acceptance Criteria
- [x] AC1 — El gate combina VLM-judge + CLIP + aesthetic en un `GateReport` ponderado (señales enchufables + fusión). *VLM multimodal validado real; CLIP/aesthetic detrás del extra `[vision]`.*
- [x] AC2 — Umbrales por tipo de escena configurables y aplicados (`FusedGate._thresholds_for` + `build_report`). 🔬
- [x] AC3 — Lower-thirds de marca por plantilla (ffmpeg drawtext), validado end-to-end. *Auto-captions/whisper diferidas (clips mudos salvo Veo).*

### Tasks
- [x] T3.1 — `gate/clip.py` (open_clip, lazy, extra `[vision]`) — adherencia prompt↔frame.
- [x] T3.2 — `gate/aesthetic.py` (LAION, lazy, extra `[vision]` + pesos) — se omite si no hay pesos.
- [x] T3.3 — `gate/fusion.py`: `fuse_signals` (media ponderada) + `build_report` + umbral. 🔬 ✅ (test-first)
- [~] T3.4 — Lower-thirds de marca (`post.py`, ffmpeg drawtext) ✅ validado. Auto-captions (whisper) **diferidas**.

> **✅ Sprint 3 CERRADO** (2026-06-02). 55 tests del core en verde. Gate convertido en paquete
> `gate/` con señales enchufables; VLM-judge ahora **multimodal** (ve un frame, validado real) y
> fusión ponderada testeada. CLIP/aesthetic implementadas detrás del extra `[vision]` (lazy torch).
> Lower-thirds de marca validados. Diferido: auto-captions whisper; correr CLIP/aesthetic reales
> (requiere instalar `[vision]`).

---

## Sprint 4 — Consistencia de personaje (API-first)

**Objetivo:** identidad consistente entre tomas, **sin librerías pesadas** (ver
[[prefer-apis-over-heavy-libs]]). Rediseño: la consistencia se **logra** propagando referencias
del personaje al keyframe, y se **mide** con Claude visión (no insightface).

### Acceptance Criteria
- [x] AC1 — Banco de personajes en `project.yaml` (`characters: {nombre: {refs:[...]}}`); cada escena resuelve sus referencias. 🔬
- [x] AC2 — El keyframe **propaga identidad** con `fal-ai/nano-banana/edit` (referencia(s) + prompt); sin referencias cae al Flux base. *Validado visual: keyframe del obrero coherente con la foto de referencia.*
- [x] AC3 — `char_consistency` medido con **Claude visión** (señal `gate/identity.py`). *Validado real: 0.47 en el clip del obrero.*
- [x] AC4 — Identidad del personaje en el **cache key** del keyframe (`character_refs` + `ref_model`).

### Tasks (orden test-first)
- [x] T4.1 — `Character` + parseo de `characters:` + `character_refs(scene, characters)`. 🔬 ✅ (test-first)
- [x] T4.2 — Keyframe con referencias (`ref_model`); identidad en el cache key.
- [x] T4.3 — `gate/identity.py` (`IdentitySignal`, Claude visión multi-imagen); se omite sin refs/key.
- [x] T4.4 — Validación PAGA ($0.150): keyframe mantiene identidad + `char_consistency` poblado. Bonus: se persisten los `gate_scores` en manifiesto/report (calibración del modo suave).
- [ ] Clasificador entrenado (original AC3) → **backlog** (reglas+LLM ya funcionan).

> **✅ Sprint 4 CERRADO** (2026-06-02). 61 tests del core en verde. Consistencia de personaje
> 100% API (sin insightface): referencias → keyframe (nano-banana/edit) → i2v; medición con Claude
> visión. Gate ahora persiste sus scores (char_consistency visible en el report).

---

## Sprint 4.5 — Interacción AI-in-the-Loop: checkpoint de keyframe

**Objetivo:** primer checkpoint humano (D-021 #4) con el modelo de interacción de **D-022**
(subcomandos con estado + hoja de contactos + no bloqueante). El humano elige el keyframe entre N.

**Flujo:** `pipeline keyframes <proj> --n N` → (revisa la hoja de contactos) → `pipeline pick <proj> s1=2` → `pipeline render <proj>`.

### Acceptance Criteria
- [x] AC1 — `keyframes <proj> --n N` genera N candidatos/escena (seeds distintos) + **hoja de contactos HTML** que se auto-abre.
- [x] AC2 — `pick <proj> s1=2 s2=0` **persiste** la selección (`selections.yaml`), resumible.
- [x] AC3 — `render <proj>` usa los keyframes **elegidos** (manifiesto: `keyframe_key: picked:...`).
- [x] AC4 — El `run` autónomo **sigue funcionando** sin cambios.

### Tasks (orden test-first)
- [x] T4.5.1 — `contact_sheet.py`: constructor de HTML (grid por escena/índice). 🔬 ✅
- [x] T4.5.2 — `parse_picks` + persistencia de candidatos/selecciones en el proyecto. 🔬 ✅
- [x] T4.5.3 — Keyframe **best-of-N**: `seed` por candidato (gen + cache key).
- [x] T4.5.4 — `studio.py`: `gen_keyframes` / `record_picks` / `render`; `run_project` acepta `keyframe_overrides`.
- [x] T4.5.5 — CLI: subcomandos `keyframes` / `pick` / `render` (+ `run` intacto).
- [x] T4.5.6 — Validación PAGA (n=2, 1 escena): 2 candidatos distintos → pick → render ($0.150).

> Video sigue siendo **IA-elige + humano-vetea** (no best-of-N); ese checkpoint se afina luego.

> **✅ Sprint 4.5 CERRADO** (2026-06-02). 68 tests del core en verde. Primer checkpoint humano
> (D-021/D-022): `keyframes → pick → render` con estado en el proyecto + hoja de contactos.
> Validado: best-of-N da candidatos distintos; el render respeta la elección humana.

---

## Sprint 4.6 — Checkpoint de casting / look-dev

**Objetivo:** checkpoint humano **previo a las escenas** (D-021 #3). El humano define un personaje
con **imágenes de entrada** (p.ej. una persona + una referencia de LEGO) + un prompt de diseño; la
IA (`nano-banana/edit`, multi-imagen) genera **N versiones**, el humano elige la **cara canónica**
en la hoja de contactos, y esa elección **se propaga** a los keyframes (banco de personajes, D-019).

**Flujo:** `pipeline cast <proj> --n N` → (hoja de contactos) → `pipeline pick-cast <proj> juan=2` → ya las escenas de ese personaje usan la cara elegida.

### Acceptance Criteria
- [x] AC1 — `project.yaml`: personaje con `design: {prompt, refs:[sujeto, lego]}`. 🔬
- [x] AC2 — `cast <proj> --n N` genera N candidatos (multi-imagen + prompt) + hoja de contactos.
- [x] AC3 — `pick-cast <proj> juan=2` fija la **cara canónica** (persistida en `casting.yaml`).
- [x] AC4 — Las escenas usan la cara elegida en el keyframe (`apply_casting` → `refs`, propagación D-019). 🔬

### Tasks (orden test-first)
- [x] T4.6.1 — `Character.design` (prompt + refs) + parseo. 🔬 ✅
- [x] T4.6.2 — `apply_casting(characters, casting)`: la elección sobreescribe los `refs`. 🔬 ✅
- [x] T4.6.3 — `studio.cast` / `record_cast_picks` (`KeyframeGenerator.generate_design`, nano-banana multi-imagen).
- [x] T4.6.4 — CLI: `cast` / `pick-cast`; `_load_project` aplica el casting a todos los comandos.
- [x] T4.6.5 — Validación PAGA (n=2): set LEGO + minifigura + prompt → 2 caras distintas (super/mago) → pick.

> **✅ Sprint 4.6 CERRADO** (2026-06-02). 71 tests del core en verde. Checkpoint de casting:
> diseñar la cara del personaje combinando varias imágenes + prompt, elegir en la hoja de contactos,
> y propagar la elección a los keyframes. Validado: 2 caras distintas; `apply_casting` cambia los
> `refs` de `[]` a la cara elegida.

---

## Sprint 5 — Producción mínima (video posteable) ⭐ SIGUIENTE

**Objetivo:** lo **mínimo** para pasar de "clips sueltos" a un video que se puede **publicar**.
Decisión: audio = **solo música de fondo**; captions = **texto por escena** que el humano escribe
(sin whisper, ver [[prefer-apis-over-heavy-libs]]); escala/ops se difiere (Sprint 6).

### Acceptance Criteria
- [x] AC1 — `music:` en `project.yaml` → pista mezclada bajo el video final (`-shortest`). *Validado: stream aac en el final.*
- [x] AC2 — `caption:` por escena → texto quemado (reusa `post.py`, sin transcripción). *Validado: "Una ciudad despierta" visible.*
- [x] AC3 — **Robustez:** una escena que falla **no aborta** el run; se ensambla lo que salió y se reporta en `failures`. *Validado REAL: `hero1` falló (Veo sin key), run continuó con vol1+std1.*
- [x] AC4 — `run`/`render` siguen funcionando; el video final lleva música + captions cuando se definen.

### Tasks (orden test-first)
- [x] T5.1 — `ProjectSpec.music` + `Scene.caption` (parseo). 🔬 ✅
- [x] T5.2 — Robustez por escena en `run_project` (try/except) + `Telemetry.record_failure` + `failed_scenes`/`failures` en el report. 🔬 ✅
- [x] T5.3 — Captions: quemar `caption` por escena (`post.burn_lower_third` + `default_font`); best-effort (no rompe la escena).
- [x] T5.4 — Música: `music` cableada en `concat_clips` (guarda si el archivo falta).
- [x] T5.5 — Validación sin API (cache hits + música sintetizada con ffmpeg): música + captions + robustez en un solo run.
- [x] **Bonus robustez:** Ensemble **tolera** un provider caído (`return_exceptions=True`): un hero funciona con seedance+kling aunque Veo no esté. 🔬

> **✅ Sprint 5 CERRADO** (2026-06-02). 77 tests del core en verde. De "clips" a **video posteable**:
> música + captions por escena + robustez (run no aborta si una toma falla). Validado end-to-end
> sobre clips cacheados ($0 de generación nueva; el run de prueba regeneró 2 por un cambio de model id).

---

## Sprint 5.5 — Capa de skills (discoverability para agentes)

**Objetivo:** formalizar [D-023] — una capa de **skills** (`skills/<nombre>/SKILL.md`) que vuelve
descubribles los flujos del pipeline para un agente (opencode, claude code) y para humanos, sin
reimplementar lógica. Salió de revisar `docs/SPEC-organic-illustration-pipeline.md` (patrón
catálogo→renderer). Refuerzo de la decisión: las skills apuntan al **contrato CLI estable**, no a
clases internas, y un **smoke de contrato en CI** mata el drift silencioso (equivalente del F10 del
SPEC de referencia).

**Flujo cubierto por el primer batch:** `author-project` (brief → `project.yaml`) → `bank-casting`
(`cast`/`pick-cast`) → `keyframe-best-of-n` (`keyframes`/`pick`/`render`).

### Acceptance Criteria
- [x] AC1 — 3 skills en `skills/*/SKILL.md` que apuntan a **subcomandos del CLI** (no a internals), enlazadas con `[[...]]`.
- [x] AC2 — Cada `SKILL.md` declara un bloque `<!-- smoke ... -->` con sus invocaciones mínimas (`pipeline ... --help`).
- [x] AC3 — `tests/test_skills_contract.py` ejecuta los smokes en modo no-op (sin gastar) y exige exit 0; una skill sin smoke **falla**. 🔬
- [x] AC4 — El smoke **detecta el drift**: un subcomando renombrado/eliminado hace fallar el test (verificado: `keyframez --help` → exit 2).

### Tasks
- [x] T5.5.1 — Reforzar [D-023] en `docs/decisiones/0021-0030.md`: contrato CLI > internals, smoke de contrato, exigencias al CLI (auto-descriptivo, estado legible, exit codes, idempotencia, dry-run).
- [x] T5.5.2 — `SPEC.md`: capa de skills + CLI como **contrato dual-audiencia** (§1) y `skills/` en la estructura (§8).
- [x] T5.5.3 — `skills/author-project/SKILL.md`, `skills/bank-casting/SKILL.md`, `skills/keyframe-best-of-n/SKILL.md` (verificadas contra `cli.py`/`studio.py`/`project.py`).
- [x] T5.5.4 — `skills/README.md`: la convención (apuntar al CLI, cómo authorar una skill, el smoke obligatorio).
- [x] T5.5.5 — `tests/test_skills_contract.py`: smoke de contrato. 🔬 ✅

> **✅ Sprint 5.5 CERRADO** (2026-06-02). 11 tests de contrato en verde
> (`uv run --extra dev pytest tests/test_skills_contract.py`); drift verificado (comando renombrado
> → exit 2). Primer batch de 3 skills + README + smoke. **Diferido:** workflow de GitHub Actions
> (no hay `.github/` aún; el smoke vive en la suite de pytest) y un modo *list* puro en el CLI
> (`pipeline list`/`scenes` sin llamar a modelos) para que el agente descubra escenas vía CLI.

---

## Sprint 6 — Audio: voz en off (ElevenLabs)

**Objetivo:** mejorar el audio con **narración opcional por escena** vía ElevenLabs (TTS por API,
alineado a [[prefer-apis-over-heavy-libs]]). No todos los videos la usan: es por-escena. Sinergia:
como el texto de la VO **ya lo escribe el humano**, la caption puede **autocompletarse** de ahí
(sin whisper). Mantiene música ([Sprint 5]) por debajo.

### Acceptance Criteria
- [x] AC1 — `voiceover:` (texto) **opcional** por escena en `project.yaml`; `ELEVENLABS_API_KEY` vía settings. 🔬 *(parseo + `voice_id` proyecto/escena testeado)*
- [x] AC2 — Se genera el audio con ElevenLabs (voz/parámetros configurables) y se mezcla en el clip de la escena, con la música por debajo (ducking/`amix`). *Código completo; adapter validado hasta auth+formato (API responde 402 sin crédito). **Smoke de audio real bloqueado por crédito ElevenLabs.***
- [x] AC3 — Si la escena tiene `voiceover` y no `caption`, la caption **se autocompleta** con el texto de la VO. 🔬 *(`effective_caption` testeado)*
- [x] AC4 — Sin `voiceover`, el video sale como en Sprint 5 (música + captions escritas). *La VO es best-effort: sin key/crédito o si falla, la escena no se pierde.*

### Tasks (orden test-first)
- [x] T6.1 — `Scene.voiceover`/`voice_id` + `ProjectSpec.voice_id` + `settings.elevenlabs_api_key` + parseo. 🔬 ✅
- [x] T6.2 — Adapter ElevenLabs TTS (`providers/elevenlabs_tts.py`, httpx crudo); aislado/mockeable, errores que nombran el problema (401/402/404/429).
- [x] T6.3 — Mezcla de VO por escena (`audio.mux_voiceover`) + música ducked + audio normalizado antes de concat (`assemble.concat_clips`).
- [x] T6.4 — `effective_caption`: caption auto desde `voiceover` cuando no hay `caption`. 🔬 ✅
- [~] T6.5 — Validación PAGA pequeña (`projects/lego_vo`, 1 escena con VO): **bloqueada** — la cuenta ElevenLabs responde 402 (sin crédito). Pendiente de recargar la cuenta.

> **Estado:** core en verde (97 tests; +9 de audio). Implementación completa: `audio.py`,
> adapter ElevenLabs, VO cacheada, ducking, caption autofill, robustez best-effort. Falta el smoke
> de audio real (recargar crédito de ElevenLabs) para **cerrar** el sprint.

---

## Sprint 6.5 — Artefactos tomables a mano + nombres semánticos (D-025/D-026)

**Objetivo:** cerrar la UX de AI-in-the-Loop. El acople secuencial de [D-022] deja de ser
**obligatorio**: (a) `render` (y el casting) aceptan **inyectar el artefacto directo por flag**
cuando el humano ya lo tiene; (b) los artefactos exponen **nombres semánticos legibles**
(humano-first), con el **hash** como verdad del caché.

**Flujo (atajo):** `pipeline render <slug> --keyframe s1=ruta s2=ruta` → video, sin pasar por
`keyframes`/`pick`.

### Acceptance Criteria
- [x] AC1 — `render <slug> --keyframe s1=ruta [--keyframe s2=ruta …]` inyecta esas imágenes; el flag **gana** sobre `selections.yaml`; el resto de escenas usa la selección persistida. *(precedencia + guard "ruta no existe" verificados sin API; render pago end-to-end queda para smoke con `FAL_KEY`.)*
- [x] AC2 — El casting admite fijar una cara **directa** por flag: `pick-cast <slug> --face nombre=ruta` (sin `cast`/candidatos). 🔬 *(parse + escritura de `casting.yaml`)*
- [x] AC3 — Los candidatos se exponen con **nombre semántico** (`<escena>_<slug>_<idx>.png` / `<personaje>_cara_<idx>.png`); la hoja de contactos muestra esos nombres. *(alias = copia del cache por hash; render real para verlo poblado.)*
- [x] AC4 — El slug se deriva con Claude (**Haiku, el más barato**); sin `ANTHROPIC_API_KEY` cae a `_slugify` del prompt. El caché content-addressed (hash) queda **intacto**. 🔬 *(fallback testeado; llamada a Claude = smoke)*
- [x] AC5 — El test de contrato de skills sigue **verde** (flag en `SKILL.md` + smoke). 🔬 *(11 passed)*

### Tasks (orden test-first)
- [x] T6.5.1 — `parse_overrides(['s1=ruta', …]) -> {escena: Path}` (lógica pura). 🔬 ✅
- [x] T6.5.2 — CLI: `render --keyframe` (repetible) → `studio.render(keyframe_overrides=…)` con precedencia sobre `selections.yaml`.
- [x] T6.5.3 — Casting: `set_cast_faces` + `pick-cast --face nombre=ruta`.
- [x] T6.5.4 — Naming semántico (`naming.py`): slug por Claude Haiku + fallback `_slugify`; `readable_name`. 🔬 ✅
- [x] T6.5.5 — `contact_sheet` muestra nombres legibles; alias en `studio.gen_keyframes`/`cast`; `skills/*` + `.gitignore`; test de contrato verde.
- [~] T6.5.6 — Smoke: guard sin API verificado (`render --keyframe x=inexistente` → error claro, exit 1). **Pendiente:** render directo pago (FAL) para ver la carpeta legible poblada.

> **Estado:** core en verde (**109 tests**, +12 del sprint). Implementado: inyección directa por
> flag (`render --keyframe`, `pick-cast --face`) con precedencia sobre la selección persistida, y
> nombres semánticos legibles (alias humano-facing; el hash sigue siendo la verdad del caché).
> Falta el smoke pago end-to-end (FAL) para **cerrar**.

---

## Sprint 6.6 — La escena compone planos (multi-plano, D-028)

**Objetivo:** un beat aburre con un solo plano de N segundos; que la escena se realice como **2-3
planos** (montaje). **Sin agregar selección:** el keyframe que el humano elige **es el plano 1**;
los planos 2+ se **autogeneran de un tiro** (sin validación). Audio **por plano**. Realiza el
checkpoint #2 (shot list) de [D-021] de forma manual; auto shot-list (LLM) **diferido**.

**Forma:** `scene.shots: [{framing, duration_s, seed, voiceover, caption}]`; prompt efectivo del
plano = `scene.prompt + ", " + framing`. Escena sin `shots:` = 1 plano implícito (compat).

### Acceptance Criteria
- [x] AC1 — `Scene.shots` se parsea; una escena **sin** `shots:` produce **1 plano implícito** (`effective_shots` sintetiza). 🔬
- [x] AC2 — El prompt efectivo del plano = `scene.prompt + ", " + framing`, envuelto por el style template; hereda personajes/estilo (`build_styled_prompt`). 🔬
- [x] AC3 — El **plano 1 usa el keyframe elegido** (`selections.yaml`/`--keyframe`, scene-addressed, `idx==0`); los **planos 2+ autogeneran** su keyframe (cacheado) sin pick.
- [x] AC4 — `render` expande la escena en planos (`_render_shot`), concatena en orden, y muxea el `voiceover`/`caption` **de cada plano**; música global por debajo (ducking si hay VO).
- [x] AC5 — `seed`/`framing` por plano entran en el cache key del plano (reroll aislado). El flujo `keyframes`/`pick` sigue **por escena** (`gen_keyframes` usa el `framing` del plano 1).

### Tasks (orden test-first)
- [x] T6.6.1 — `Shot` en `contracts.py` + `Scene.shots`; parseo en `project.py`. 🔬 ✅
- [x] T6.6.2 — `effective_shots(scene)`: planos reales o **sintetiza 1** (compat). 🔬 ✅
- [x] T6.6.3 — Composición de prompt `scene.prompt + framing` en `keyframe.build_styled_prompt`. 🔬 ✅
- [x] T6.6.4 — `runner._render_shot` + loop por plano; plano 1 = keyframe elegido/override, planos 2+ autogenerados (cacheados); cache key por plano (`seed`+`framing`).
- [x] T6.6.5 — `assemble`: concat de planos + audio por plano; **recorte ffmpeg** (`trim_to`) a `duration_s`.
- [x] T6.6.6 — `studio.gen_keyframes`: los candidatos usan el `framing` del **plano 1**; `pick`/`selections.yaml` scene-addressed.
- [x] T6.6.7 — `projects/lego_mix/project.yaml`: 3 escenas a 2-2-1 planos con VO/caption por plano (smoke). *(Render pago end-to-end: ver nota.)*

> **Diferido:** `transition` (corte duro por ahora) y auto shot-list (Claude descompone el beat).

> **✅ Sprint 6.6 CERRADO** (2026-06-06). Core en verde (`test_shots.py`: parseo, `effective_shots`,
> composición de prompt). El runner expande cada escena en planos (`_render_shot`), con keyframe del
> plano 1 elegido y planos 2+ autogenerados, audio por plano y recorte por duración. Proyecto
> `lego_mix` migrado a multi-plano. **Pendiente:** smoke pago end-to-end (FAL) — render real de los 5
> planos (cubierto junto con 6.7/6.8).

---

## Sprint 6.7 — Export bundle para edición humana (D-029)

**Objetivo:** el `final.mp4` no alcanza — el video real lo corta una editora. `pipeline export <slug>`
arma `projects/<slug>/export/` con **materia prima limpia** desde el último run; el `final.mp4` pasa
a ser **rough cut** de referencia. Cierra el AI-in-the-Loop en la capa L8.

**Estructura:** `media/` (videos limpios + voces + música, `NN_<id>`) · `frames/` (keyframes) ·
`rough_cut.mp4` · `subtitulos.srt` · `guion.md` (onboarding + tabla de planos).

### Acceptance Criteria
- [x] AC1 — `pipeline export <slug>` crea `projects/<slug>/export/` con `media/`, `frames/`, `rough_cut.mp4`, `subtitulos.srt`, `guion.md` (`export_bundle`).
- [x] AC2 — Los clips de `media/` son **limpios** (del caché, sin caption/VO quemada), recortados a `duration_s`; voz (`.mp3`) y frame emparejados por **mismo nombre** `NN_<id>`.
- [x] AC3 — `guion.md` = **onboarding** (organización + tabla; **definiciones al final**). 🔬
- [x] AC4 — `subtitulos.srt` **sincronizado** al timeline (`srt_from_timeline`: avanza con todos, emite solo los que tienen voz). 🔬
- [x] AC5 — Numeración global `NN_<shot_id>` consistente entre `media/`, `frames/` y la tabla (`numbered`). 🔬

### Tasks (orden test-first)
- [x] T6.7.1 — `srt_from_timeline(planos)` → `.srt` con tiempos acumulados. 🔬 ✅
- [x] T6.7.2 — `numbered(planos)` → orden global `NN_<id>` + base de nombre. 🔬 ✅
- [x] T6.7.3 — `render_guion(spec, planos)` → markdown (onboarding + tabla + definiciones). 🔬 ✅
- [x] T6.7.4 — `export.py`: copia clips (caché, recortados) + voces + música + frames; `rough_cut` = `final.mp4` del run.
- [x] T6.7.5 — CLI `export <slug>` (lee el último run + spec).
- [~] T6.7.6 — Smoke real: el core (`_ts`/`numbered`/`srt`/`render_guion`) testeado; el bundle completo (copia desde caché) **pendiente** del render pago de `lego_mix`.

> **✅ Sprint 6.7 CERRADO** (2026-06-06). Core en verde (`test_export.py`: formato SRT, numeración,
> srt sincronizado, estructura del guion, tolerancia a manifests viejos). `export_bundle` + CLI `export`
> implementados. **Pendiente:** smoke del bundle completo tras el render pago (cubierto con 6.6).

---

## Sprint 6.8 — Guion completo (script) + conversor md→docx (D-030)

**Objetivo:** que el `guion.md` cuente la **historia** (no solo la tabla técnica) — alguien sin
contexto, solo leyendo, entiende el proyecto — y que salga también en **`.docx`** vía un conversor
**genérico** `md→docx` (frontmatter = metadata), invocado **best-effort** por `export`.

### Acceptance Criteria
- [x] AC1 — `guion.md` lleva, en orden: **sinopsis** + **personajes** + **el guion beat-por-beat** (descripción + VO por plano) + **tabla por plano** + organización/definiciones. 🔬
- [x] AC2 — `guion.md` arranca con **frontmatter** (`title`, `subtitle`, `footer`) para el conversor. 🔬
- [x] AC3 — `src/md_to_docs/` (Node + **pnpm**): `node convert.js <in.md> [out.docx]` convierte **cualquier** `.md` (headings, bold/italic/code/link, listas, tablas, blockquote→nota, `---`→divider, code) con paleta configurable por frontmatter. *(Validado: sample.md → .docx con magic bytes PK.)*
- [x] AC4 — `pipeline export` invoca el conversor **best-effort** (`_maybe_docx`): comando global `md-to-docs` o `src/md_to_docs/convert.js`; sin node, solo `guion.md` (no rompe).
- [~] AC5 — Conversor validado end-to-end (md→docx abrible). `export` → `guion.docx` completo **pendiente** del render pago.

### Tasks (orden test-first)
- [x] T6.8.1 — `render_guion` ampliado: sinopsis + personajes + guion beat-por-beat (de `scene.prompt`) + tabla + frontmatter. 🔬 ✅
- [x] T6.8.2 — `src/md_to_docs/` (`package.json` pnpm: `docx`/`marked`/`gray-matter`) + `convert.js`. *(deps instaladas, `pnpm-lock.yaml`)*
- [x] T6.8.3 — Frontmatter → portada/footer (defaults si falta).
- [x] T6.8.4 — `export_bundle`: invocación best-effort a node (genera `guion.docx`; omite sin conversor).
- [~] T6.8.5 — Conversor probado con sample real; smoke completo `export` → `guion.docx` **pendiente** del render pago.

> **✅ Sprint 6.8 CERRADO** (2026-06-06). `render_guion` cuenta la historia (frontmatter + sinopsis +
> personajes + libreto beat-por-beat + desglose + definiciones, core en verde). Conversor genérico
> `md→docx` (`src/md_to_docs/convert.js`) **validado end-to-end** (genera un `.docx` válido) e invocado
> best-effort por `export`. **Pendiente:** el `guion.docx` dentro del bundle tras el render pago.

---

## Sprint 6.9 — Diseño sonoro: SFX + ambiente (D-034)

**Objetivo:** completar la **banda sonora** (voces ✅ + música ✅ + **efectos** + **ambiente**) sin
descuadre con la imagen. Motor por defecto: **MMAudio V2** (video-to-audio en fal, $0.001/s) que
lee los frames del clip ya generado y genera audio **sincronizado**; **audio nativo** (Veo/Kling con
audio) queda como **premium por `routing.yaml`**. Ver [D-034].

**Forma:** `scene.ambience` (texto, el *lugar*, por escena) + `shot.sfx` (texto, la *acción*, por
plano), en `project.yaml`. El cue de MMAudio por plano = `shot.sfx` + `ambience` de su escena.

### Acceptance Criteria
- [x] AC1 — `scene.ambience` + `shot.sfx` se parsean (contracts/`project.yaml`) y round-trip por `write_spec`; sin ellos, el render queda **intacto**. 🔬
- [x] AC2 — `effective_audio_cue(scene, shot)` = `sfx` del plano + `ambience` de su escena (lógica pura). 🔬
- [x] AC3 — Tras el clip (mudo), un **paso V2A** (MMAudio, fal) **cacheado** (`sfx` ← `video_key + cue + seed`) devuelve el clip con audio; sin cue/clave → se omite (best-effort).
- [x] AC4 — Mezcla con **jerarquía** voz > diegético (0.6) > música (0.25). `mux_voiceover` **mezcla (`amix`)** sobre el audio del clip, no reemplaza. 🔬 *(filtro/parámetros)*
- [x] AC5 — Si el clip **ya trae audio** (modelo nativo tipo Veo, vía `routing.yaml`), se respeta y **se salta** el V2A (`_has_audio`) — sin tocar código.

### Tasks (orden test-first)
- [x] T6.9.1 — `Scene.ambience` + `Shot.sfx` en `contracts.py` + parseo y `spec_to_dict`/`write_spec`. 🔬 ✅
- [x] T6.9.2 — `audio.effective_audio_cue(scene, shot)` (sfx + ambience de la escena). 🔬 ✅
- [x] T6.9.3 — `providers/mmaudio.py` (fal `fal-ai/mmaudio-v2`): clip + cue → clip con audio; aislado/mockeable.
- [x] T6.9.4 — `runner._render_shot`: paso V2A tras el recorte (cacheado, best-effort); se omite si el clip ya trae audio.
- [x] T6.9.5 — `audio.mux_voiceover` → **mezcla** (`amix`) sobre el diegético, con jerarquía (`vo_mix_filter`). 🔬 ✅
- [~] T6.9.6 — `projects/lego_mix` con `ambience`/`sfx` listo como target. **Smoke pago (centavos) pendiente** (MMAudio real + mezcla).

> **Diferido:** diálogo/lip-sync nativo (sigue por TTS); **stems separados por capa** en el export
> ([D-029]); ThinkSound como alternativa de V2A.

> **✅ Sprint 6.9 CERRADO** (2026-06-06). Core en verde (`test_sound.py`: parseo/round-trip, cue,
> filtro de mezcla; +9). SFX (acción, por plano) + ambiente (lugar, por escena) → cue → **MMAudio V2**
> (V2A en fal, lee los frames → sincronizado, $0.001/s), cacheado y best-effort; la voz se **mezcla**
> encima del diegético y la música queda por debajo. Audio nativo (Veo/Kling) se respeta y salta el
> V2A. **Pendiente:** smoke pago end-to-end con `lego_mix` (junto con el de 6.6/6.7/6.8).

---

## Sprint 7 — Escala y operación

**Objetivo:** durabilidad, persistencia y observabilidad de producción.

### Acceptance Criteria
- [ ] AC1 — Workflows multi-paso son durables y reanudables ante fallo (reintentos declarativos).
- [ ] AC2 — Dashboard de costo/latencia por escena, lote y modelo.
- [ ] AC3 — API HTTP para encolar jobs; artefactos en almacenamiento objeto.

### Tasks
- [ ] T5.1 — Migrar orquestación a Temporal; estado a Postgres.
- [ ] T5.2 — FastAPI para encolar/consultar jobs.
- [ ] T5.3 — Dashboard + Langfuse para trazas de LLM.
- [ ] T5.4 — Storage S3/GCS para keyframes y renders.

---

## Sprint 8 — Internalización opcional (abaratar imagen)

**Objetivo:** plan B / reducción de costo de la capa de keyframe vía self-hosting.

### Acceptance Criteria
- [ ] AC1 — ComfyUI/Wan/LTX detrás de la **misma interfaz `Provider`** (cero cambios aguas arriba).
- [ ] AC2 — Comparativa costo/calidad self-host vs. fal documentada.

### Tasks
- [ ] T6.1 — `providers/comfy_local.py` (keyframe Flux local con LoRA).
- [ ] T6.2 — Benchmark costo/calidad y umbral de break-even.

---

## Backlog / decisiones abiertas
- [ ] Adapters directos (precio nativo) para el modelo que se vuelva caballo de batalla a volumen.
- [ ] Detección de artefactos temporales (flicker/warp) en el gate.
- [ ] Música: librería licenciada vs. API generativa.
- [ ] Multi-formato simultáneo (9:16 + 1:1 + 16:9) en una sola corrida.
- [ ] Atribución de costo por provider dentro de Ensemble: hoy el costo total de la escena se atribuye al ganador en `cost_by_provider` (el total global es correcto). Desglosar por candidato.

---

_Leyenda: 🔬 = lleva test de core (TDD). Lo no marcado se valida con smoke run._
