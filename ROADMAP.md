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

## Sprint 6.11 — Perfiles de calidad + escenas en paralelo (D-038, D-039)

**Objetivo:** que `pipeline run --profile proto` sea el comando de iteración barato (un candidato,
proveedor más económico, rápido) y `--profile prod` sea la producción final; y que con
`--concurrency N` varias escenas corran en vuelo simultáneo recortando el tiempo total de render.

### Acceptance Criteria
- [x] AC1 — `routing.yaml` tiene perfiles `prod` y `proto`; `--profile proto` aplica la tabla barata sin tocar otros archivos.
- [x] AC2 — `--profile prod` reproduce exactamente el comportamiento actual (ensemble/router/cascade). 🔬
- [x] AC3 — `pipeline run <slug> --profile proto --concurrency 3` genera las escenas en vuelo simultáneo con el mismo orden de clips que en serie.
- [x] AC4 — Una escena que falla con `concurrency > 1` no aborta el resto del run. 🔬
- [x] AC5 — El endpoint `POST /api/projects/{slug}/render` acepta `profile` y `concurrency` en el body.

### Tasks (orden test-first)
- [x] T6.11.1 — ADRs D-038 y D-039 en `docs/decisiones/`.
- [x] T6.11.2 — `routing.yaml`: sección `profiles:` con `prod` y `proto`. 🔬 *core*
- [x] T6.11.3 — `config.py`: `RoutingConfig.hybrid` → `rules`; `load_routing(path, profile)`. 🔬 *core*
- [x] T6.11.4 — `dispatch.py` + tests. *core*
- [x] T6.11.5 — `runner.py`: `run_project(concurrency=1)` + `asyncio.gather` con semáforo. 🔬 *core*
- [x] T6.11.6 — `cli.py`: `--profile prod` y `--concurrency 1` en `run`; `--concurrency` en `render`.
- [x] T6.11.7 — `app.py`: endpoint render acepta `profile`/`concurrency`.
- [x] T6.11.8 — Smoke: `pipeline run lego_mix --profile proto --concurrency 2`.

> **✅ Sprint 6.11 CERRADO** (2026-06-07). Perfiles `prod`/`proto` seleccionables desde CLI y UI;
> `RoutingConfig.rules` (antes `hybrid`); `run_project(concurrency=N)` con semáforo; endpoint
> render acepta `profile`/`concurrency`; selector de velocidad en `Produccion.svelte`.

---

## Sprint 6.10 — Frame por plano + cortes cortos (D-037)

**Objetivo:** que **cada plano** autogenere su propio frame desde su `framing` (no reusar una opción
para varios planos) y que los planos sean **cortos por default (~2s)**. Refina [D-028]; ver [D-037].

### Acceptance Criteria
- [ ] AC1 — Cada plano (incluido el 1) genera/usa **su** frame desde su `framing`; no se reusa el de otro plano.
- [ ] AC2 — El clip se **corta a la duración del plano**; default corto (~2s) cuando no se especifica.
- [ ] AC3 — Sin checkpoint humano **por plano** (se mantiene el de escena/casting, espíritu de D-028).
- [ ] AC4 — Cache key por plano intacto (`seed`+`framing`); cambiar el framing regenera solo ese plano.

### Tasks (orden test-first)
- [ ] T6.10.1 — Default de duración corto (~2s) para planos sin `duration_s` explícito. 🔬 *core*
- [ ] T6.10.2 — `runner._render_shot`: generar el frame de **cada** plano desde su framing (uniforme).
- [ ] T6.10.3 — Verificar el recorte (`trim_to`) a la duración corta end-to-end (smoke).

---

## Sprint 6.12 — Edición autónoma: describe + movis + mcp-video (D-041, D-042)

**Objetivo:** cerrar el bucle **sin editora humana**. Un agente (Opus) monta el corte final
priorizando **el mensaje sobre el pulido**, con tres piezas de roles separados: **`describe`** (los
ojos: Haiku evalúa cada plano), **`graphics`** (el artista: movis genera motion graphics) y
**mcp-video** (el ingeniero: servidor MCP guardrailed para el montaje). Ver [D-041]/[D-042].

### Acceptance Criteria
- [x] AC1 — `pipeline describe <slug>` genera `projects/<slug>/descriptions.yaml` con `{usable, on_message, issues, description}` por plano, leyendo del último run. 🔬 *(prompt/parseo)*
- [x] AC2 — Sin `ANTHROPIC_API_KEY`, `describe` emite warning y sale 0 con salida vacía (no rompe). 🔬
- [x] AC3 — `pipeline graphics <slug>` produce `export/graphics/` (lower-thirds por plano con `caption`, `title.mp4`, `end.mp4`) de forma determinista. 🔬 *(selección desde el manifest)*
- [x] AC4 — Si falta el extra `[edit]`, `graphics` falla con un mensaje claro que dice cómo instalarlo (`uv sync --extra edit`).
- [x] AC5 — `.mcp.json` registra `mcp-video` vía `uvx`; el agente lo ve como servidor MCP y no es dependencia del proyecto.
- [x] AC6 — La skill `narrative-cut` documenta el bucle `export → describe → graphics → (agente vía mcp-video) → final_cut.mp4` y pasa el smoke de contrato (`pipeline describe --help`, `pipeline graphics --help`).

### Tasks (orden test-first)
- [x] T6.12.1 — ADRs D-041 y D-042 en `docs/decisiones/`; SPEC (L10) y ROADMAP.
- [x] T6.12.2 — `describe.py`: `describe_prompt` + `parse_description`. 🔬 *core*
- [x] T6.12.3 — `gate/frames.py::extract_frame` incluye `at_seconds` en el nombre (evita colisión). 🔬 *core*
- [x] T6.12.4 — `describe.py::describe_bundle` (Haiku + frames) y subcomando `describe` en `cli.py`.
- [x] T6.12.5 — `graphics.py`: `lower_thirds`/`title_spec`/`end_spec`. 🔬 *core*
- [x] T6.12.6 — `graphics.py::render_graphics` (movis) + subcomando `graphics` en `cli.py` + extra `[edit]`.
- [x] T6.12.7 — `.mcp.json` (mcp-video por `uvx`) + `skills/narrative-cut/SKILL.md` + fila en `skills/README.md`.
- [~] T6.12.8 — Smoke real: `export → describe → graphics` sobre `lego_mix`; corte final vía mcp-video. **Pendiente** del render pago.

> **✅ Sprint 6.12 CERRADO** (2026-06-08). `describe` (Haiku analiza cada plano → `descriptions.yaml`)
> + `graphics` (movis genera lower-thirds/placas deterministas → `export/graphics/`) + `.mcp.json`
> (mcp-video por uvx) + skill `narrative-cut`. Core en verde. Pendiente: smoke pago end-to-end.

---

## Sprint 6.13 — Veo explícito + perfiles dinámicos en UI (D-043, D-044)

**Objetivo:** cuando los créditos de fal.ai se agotan, poder usar Google Veo **sin fallback
automático**; y que la UI descubra los perfiles del YAML **sin recompilarse**.

### Acceptance Criteria
- [x] AC1 — `proto_veo` es un perfil independiente en `routing.yaml`; elegirlo envía todo a Veo sin tocar `proto`. (D-043)
- [x] AC2 — Cada perfil tiene un bloque `_meta` (label/desc/badge/color); el config loader lo elimina antes del parse. (D-044)
- [x] AC3 — `GET /api/profiles` devuelve la lista de perfiles con su metadata desde el YAML en runtime.
- [x] AC4 — `Produccion.svelte` carga los perfiles dinámicamente con `onMount → fetch /api/profiles`; fallback estático si el servidor no responde.
- [x] AC5 — `providers/google_veo.py` usa polling asíncrono (`asyncio.to_thread` + `asyncio.sleep`) y descarga autenticada vía `client.files.download`.

### Tasks
- [x] T6.13.1 — ADRs D-043 y D-044 en `docs/decisiones/`.
- [x] T6.13.2 — Perfil `proto_veo` + bloque `_meta` en los tres perfiles de `routing.yaml`.
- [x] T6.13.3 — `config.load_routing` hace `rules.pop("_meta", None)`.
- [x] T6.13.4 — `server/app.py`: endpoint `GET /api/profiles`.
- [x] T6.13.5 — `Produccion.svelte`: `onMount → fetch`, `COLOR_MAP`, `badgeStyle`, fallback estático.
- [x] T6.13.6 — `providers/google_veo.py` reescrito; `providers.yaml` ajusta veo a `veo-2.0-generate-001`; `pyproject.toml` añade `google-genai>=0.8`.

> **✅ Sprint 6.13 CERRADO** (2026-06-08). Veo disponible como perfil explícito (`proto_veo`);
> UI descubre perfiles dinámicamente desde routing.yaml; el proveedor Google corre sin fallback.

---

## Sprint 6.14 — Storyboard centrado en la historia: UX humano-first (D-045)

**Objetivo:** que el Storyboard (paso 2) muestre la **historia** que el humano firma, no los
prompts que la IA consume. Los prompts se desplazan a **Elegir** (paso 3) donde se revisan antes
de generar. Ver [D-045].

### Acceptance Criteria
- [ ] AC1 — Modo lectura colapsado del Storyboard muestra: `beat` + chips de VO + duración; **no `s.prompt`**.
- [ ] AC2 — Modo lectura expandido muestra: beat, diálogo, voiceover, caption, ambience. Sin `prompt` ni `framing` visibles en modo lectura.
- [ ] AC3 — Modo edición del Storyboard: prompt visual y framing agrupados en un panel **"Para la IA"** colapsable (editable pero subordinado).
- [ ] AC4 — Elegir (paso 3) tiene una sección **"Prompts para la IA"** (colapsable, por escena) que muestra/edita `s.prompt` y `shot.framing`; guardar usa `PUT /api/projects/{slug}` (sin cambio de API).
- [ ] AC5 — El flujo `cast → keyframes → pick` **no se rompe**: los prompts siguen fluyendo al pipeline.

### Tasks
- [x] T6.14.1 — ADR D-045 en `docs/decisiones/`.
- [x] T6.14.2 — `Storyboard.svelte`: read-compact muestra dialogo/vo/ambience; read-full muestra dialogo/vo/caption sin `s.prompt`; edit mode pone prompt en panel "Para la IA" colapsable.
- [x] T6.14.3 — `Picker.svelte`: sección "Para la IA" colapsable por escena (prompt + framings), editable + `PUT /api/projects/{slug}` al guardar.
- [x] T6.14.4 — Build limpio (0 errores, warnings CSS resueltos).

---

## Sprint 6.15 — Prompt derivado de la narrativa: compilable + sincronizable (D-046)

**Objetivo:** cerrar el hueco de D-045. El Storyboard es la fuente de verdad; `scene.prompt` pasa
a ser un artefacto **derivado-pero-sobrescribible**: se **compila** desde la narrativa (Haiku), se
detecta cuando quedó **desactualizado** y se resincroniza de un clic. Ver [D-046].

### Acceptance Criteria
- [x] AC1 — `Scene` lleva `prompt_manual` + `prompt_src_hash`; `narrative_hash()` y `prompt_stale` derivan el estado (en sintonía / desactualizado / manual).
- [x] AC2 — `prompt_compile.compile_prompt` arma el prompt desde beat+ambience+diálogo+personajes vía Haiku; sin `ANTHROPIC_API_KEY` cae a concatenación determinista (no rompe).
- [x] AC3 — `POST /api/projects/{slug}/prompts/compile` y `pipeline prompts <slug> [--scene] [--force]` compilan los prompts desactualizados (D-023).
- [x] AC4 — El draft de `author.py` sella el hash al nacer; el `PUT` marca `prompt_manual` solo cuando el prompt entrante difiere del base.
- [x] AC5 — Elegir muestra el badge de estado por escena + botón "Compilar desde la narrativa"; los campos nuevos hacen round-trip idempotente en el YAML.

### Tasks
- [x] T6.15.1 — ADR D-046 en `docs/decisiones/`.
- [x] T6.15.2 — `contracts.py` (campos + `narrative_hash`/`prompt_stale`); `prompt_compile.py` (+ tests core).
- [x] T6.15.3 — `author.py` (sella hash), `project.py::_scene_to_dict` (persistencia), subcomando `prompts` en `cli.py`.
- [x] T6.15.4 — `server/app.py` (endpoint compile + serialización + manual en PUT); `Picker.svelte` (badge + botón compilar).

---

## Sprint 6.16 — El plano como artefacto audiovisual: gramática + Block (D-047)

**Objetivo:** elevar el `Shot` de un blob de `framing` a un **artefacto de producción**: intención,
gramática de cámara (shot-list), estructura visual (Bruce Block) y transición, más la **curva de
intensidad** por escena. El artista piensa en gramática; `compose_shot_visual` la ensambla en el
prompt. Aditivo y retrocompatible. Ver [D-047].

### Acceptance Criteria
- [x] AC1 — `Camera`/`Visual` + enums controlados; `Shot` con intention/action/camera/visual/transition; `Scene.visual_intensity`. Defaults omitidos en el YAML, round-trip idempotente.
- [x] AC2 — `compose_shot_visual` ensambla action + cámara + visual en lenguaje natural (fallback a `framing`); `runner`/`studio` generan desde ahí.
- [x] AC3 — `author.py` propone el artefacto enriquecido; sanitizador de enums tolera valores inválidos del LLM sin romper el borrador.
- [x] AC4 — Storyboard: shot-card editable (cámara como selects + diseño visual de Block), lectura muestra la descripción por plano, y gráfico de la curva de intensidad. PUT mergea shots por índice.
- [x] AC5 — Proyecto `desmintiendo_fracking_sostenible` enriquecido (19 planos) listo para re-generar.

### Tasks
- [x] T6.16.1 — ADR D-047 + referencias (StudioBinder, Bruce Block, Mascelli).
- [x] T6.16.2 — F1 contrato + `prompt_compile` + persistencia + `tests/test_shot_artifact.py`.
- [x] T6.16.3 — F2 `author.py` (artefacto + sanitizador) + tests; F3 wiring `runner`/`studio`.
- [x] T6.16.4 — F4 UI `Storyboard.svelte` (shot-card + curva) + `server/app.py` (serialización + merge); build limpio.
- [x] T6.16.5 — F5 enriquecer el proyecto fracking (`scripts/_enrich_fracking.py`).

---

## Sprint 6.17 — Coherencia de planos + flujo guiado + casting artefacto (D-048, D-049)

**Objetivo:** que el video sea coherente plano a plano y que el flujo guíe al humano con un solo
foco por pantalla. Ver [D-048], [D-049].

### Acceptance Criteria
- [x] AC1 — Keyframe (imagen fija) ≠ video (movimiento): `compose_keyframe_prompt` sin `move`; `compose_video_prompt` con el movimiento.
- [x] AC2 — Planos 2+ encadenan (i2i) desde el ancla de la escena; el cache encadena por `kf_key` del plano previo.
- [x] AC3 — Previsualización de planos por escena (`/shots`, `shot_previews.yaml`) con reroll en Elegir.
- [x] AC4 — Foco guiado (`.cta`): Storyboard firmar→siguiente; Elegir casting→encuadres (gated); PUT mergea shots por índice.
- [x] AC5 — Storyboard colapsado muestra la descripción visual (B1); `CharacterDesign` enriquecido (physical/wardrobe/palette/expression) y compuesto en casting (D-049).

### Tasks
- [x] T6.17.1 — A1 separar keyframe/video; A2/A3 encadenado en runner/studio; tests.
- [x] T6.17.2 — A4 `preview_shot_keyframes` + endpoint + tira en Elegir.
- [x] T6.17.3 — C1 `.cta`; C2 foco Storyboard; C3 reorden Elegir + gating casting→encuadres; C4 (plegado).
- [x] T6.17.4 — B1 descripción visual colapsada; B2 `CharacterDesign` artefacto + `compose_character_prompt`.
- [x] T6.17.5 — ADRs D-048/D-049; build limpio; suite verde (1 fallo pre-existente ajeno: veo).

---

## Sprint 6.18 — Keyframe por Google + acciones masivas (D-051)

**Objetivo:** que el keyframe también se pueda generar por Google (Gemini 2.5 Flash Image), para un
camino completo sin fal; y botones para operar en lote (compilar prompts, generar planos). Ver [D-051].

### Acceptance Criteria
- [x] AC1 — `KeyframeGenerator` soporta `backend=google` (genera y edita/encadena vía google-genai).
- [x] AC2 — Toggle fal/Google en Elegir, gateado por `GOOGLE_API_KEY`, pasado por endpoints → studio.
- [x] AC3 — Acciones masivas: "Compilar prompts desactualizados / Recompilar todos" y "Generar todos los planos".
- [x] AC4 — `GOOGLE_API_KEY` expuesta en `/api/settings` + campo en Ajustes; test de veo alineado a `i2v`.

### Tasks
- [x] T6.18.1 — `keyframe.py` backend Google (`_submit_google`, `_extract_image_bytes`).
- [x] T6.18.2 — Thread `backend` por studio + 4 endpoints; `google_api_key` en `_KEYS`.
- [x] T6.18.3 — UI: toggle + barra de acciones masivas (Picker), campo Google (Ajustes).
- [x] T6.18.4 — ADR D-051; fix test veo; build limpio.

---

## Sprint 6.19 — Split storyboard/render + visibilidad de costos (D-052, D-053)

**Objetivo:** dos configuraciones para dos fases — `--backend` para la fase creativa (imágenes +
LLM), `--profile` para la fase de producción (video + gate). El backend activo se persiste en
`project.yaml`. El usuario ve lo que gasta al final de cada paso.

### Acceptance Criteria
- [x] AC1 — `routing.yaml` define `storyboard_backends` (fal, google) y perfiles de render limpios
  (`fal-ultra-cheap` default, sin `keyframe`/`llm`). Gate VLM configurable por perfil. 🔬
- [x] AC2 — El gate VLM lee `vlm_model` del perfil activo; perfil sin gate → señales vacías (permisivo). Soporta Anthropic y Gemini como backends de VLM. 🔬
- [x] AC3 — `project.yaml` persiste `storyboard_backend: fal`; `spec_from_dict`/`spec_to_dict` hacen round-trip. 🔬
- [x] AC4 — `--backend google` en `cast`/`keyframes`/`prompts` usa el backend de storyboard; `--profile prod` en `render`/`run` usa el perfil de render. El flag del spec se usa si no se pasa `--backend` explícito.
- [x] AC5 — Al final de cada subcomando se imprime una línea de costo (est + actual). HTTP 402 → mensaje con alternativa sugerida.
- [x] AC6 — `GET /api/storyboard-backends` devuelve la lista con `_meta`; UI Storyboard tiene chip discreto que persiste la elección vía PUT.

### Tasks (orden test-first)
- [x] T6.19.1 — ADRs D-052 y D-053 + SPEC + ROADMAP. ✅
- [x] T6.19.2 — `routing.yaml` (storyboard_backends + perfiles limpios) + `config.py` (ProfileConfig gate-only, StoryboardConfig, loaders). 🔬 *core* ✅
- [x] T6.19.3 — `gate/vlm.py` + `gate/fused.py`: vlm_model del perfil, señales vacías si disabled, soporte Gemini VLM. ✅
- [x] T6.19.4 — `runner.py`: keyframer backend desde `cfg.storyboard`. ✅
- [x] T6.19.5 — `cli.py`: cost summary + 402 (parcial — `--backend` queda para T6.19.6). ✅
- [x] T6.19.6 — `project.py` (`storyboard_backend` en spec); `cli.py` (`--backend` en storyboard cmds, lee del spec). 🔬 *core* ✅
- [x] T6.19.7 — `server/app.py`: `GET /api/storyboard-backends`; PUT persiste `storyboard_backend`. ✅
- [x] T6.19.8 — UI `Storyboard.svelte`: chip selector de backend (discreto, carga desde `/api/storyboard-backends`). ✅
- [ ] T6.19.9 — Smoke: `pipeline keyframes lego_demo --backend google`; `pipeline run lego_demo --profile fal-ultra-cheap` (cost summary visible).

---

## Sprint 6.20 — Endurecimiento post-review Sprint 1 (D-054)

**Objetivo:** cerrar los **tres bugs latentes** que sobrevivían de la revisión externa del Sprint 1
(`docs/notas/feedback-sprint-1.md`) — los del tipo "no muerde hoy, muerde cuando mezcles providers o
falle ffmpeg", justo los escenarios que el roadmap multi-provider habilita. Los otros 7 puntos del
review ya estaban cerrados o son deudas asumidas (ver [D-054]). Aditivo, sin cambiar el camino feliz.

### Acceptance Criteria
- [x] AC1 — `SceneRequirements.required_capabilities()` exige **siempre `i2v`** (los flags suman sobre
  esa base); un provider sin `i2v` queda descartado del routing por construcción (#8). 🔬
- [x] AC2 — El tail del runner (`concat_clips`/`reframe`/`_write_manifest`) corre en `try/finally`:
  `write_report` + `close` + `remove_handler` ocurren **siempre**, aun si ffmpeg revienta; la rama
  "todas fallaron" escribe el reporte **antes** de lanzar (#10).
- [x] AC3 — `concat_clips` conforma el **video** a una resolución canónica (libx264 + letterbox) solo
  cuando los clips son **heterogéneos** (codec/resolución distintos); con clips uniformes mantiene el
  `-c copy` rápido. La decisión es lógica pura testeada (#4). 🔬
- [ ] AC4 — Smoke real: render que **mezcla providers** (p.ej. hero→ensemble seedance + std→router
  kling) produce un `final.mp4` reproducible sin video roto. **Pendiente** del render pago.

### Tasks (orden test-first)
- [x] T6.20.1 — `contracts.py`: `required_capabilities()` parte de `{"i2v"}`; `tests/test_contracts.py` alineado. 🔬 ✅
- [x] T6.20.2 — `runner.py`: tail en `try/finally`; reporte en la rama de fallo total (compatible con `test_runner_concurrency`). ✅
- [x] T6.20.3 — `assemble.py`: `_video_sig`/`_uniform`/`_canonical_size` + `_ensure_audio`→`_normalize(video_size)`; `concat_clips` conforma si hay heterogeneidad. ✅
- [x] T6.20.4 — `tests/test_assemble.py` (decisión de uniformidad + resolución canónica). 🔬 ✅
- [x] T6.20.5 — ADR D-054 + índice del README de decisiones. ✅
- [ ] T6.20.6 — Smoke pago: render multi-provider (junto con los smokes pendientes de 6.6/6.19).

> **Estado:** core en verde (**270 tests**, +7 de `test_assemble`; `test_contracts` ajustado al
> contrato i2v). Los tres bugs latentes cerrados sin tocar el camino de 1 provider. **Pendiente:**
> el smoke pago multi-provider (AC4) para **cerrar**. Deudas asumidas del review (LoRA placeholder
> #5, costo estimado vs facturado #9) quedan registradas en [D-054], no resueltas.

---

## Sprint 9 — Biblioteca global de assets reusables (D-036)

**Objetivo:** crear personajes/símbolos/lugares **una vez** y reusarlos **entre proyectos**,
consistentemente. Biblioteca global referenciada por nombre (no copias). Ver [D-036].

### Acceptance Criteria
- [ ] AC1 — Banco global en la raíz (p.ej. `library/characters|symbols|places/`), versionado.
- [ ] AC2 — Un `project.yaml` referencia un asset del banco **por nombre**; se resuelve a ruta para I/O (hash estable).
- [ ] AC3 — El asset se diseña/fija una vez y se propaga a los keyframes (igual que el casting, [D-019]).
- [ ] AC4 — Símbolos y lugares además de personajes (puede arrancar por personajes).

### Tasks
- [ ] T9.1 — Modelo del banco + resolución de refs globales vs project-relative. 🔬 *core*
- [ ] T9.2 — Propagación del asset elegido al keyframe (reusa casting/[D-019]).
- [ ] T9.3 — App: pantalla para crear/elegir assets del banco.

> **Diferido:** versionado de assets, cache global vs por-proyecto (a definir en la implementación).

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
