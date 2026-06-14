# ROADMAP — Pipeline de Video IA

> Acompaña a [`ARCHITECTURE.md`](./ARCHITECTURE.md) (cómo) y [`PRD.md`](./PRD.md) (qué/para-quién).
> Cada sprint tiene **objetivo**, **acceptance criteria** (AC) verificables y **tasks**; marca `[x]`
> al completar. Los sprints **cerrados** se archivan en [`docs/roadmap/`](docs/roadmap/).

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

## Estado

Dos tracks: **pipeline** (el motor, este archivo) y **app** (el Studio, [`app/ROADMAP.md`](app/ROADMAP.md)).

### Cerrado (histórico)

Sprints 1–6.37 del pipeline están **cerrados**: MVP vertical → caché/proyecto → multi-modelo → gate duro → consistencia de personaje → checkpoints interactivos → animatic/motor → Studio Svelte. El detalle completo (AC, tasks, notas de cierre) vive en
[`docs/roadmap/pipeline-historico.md`](docs/roadmap/pipeline-historico.md).

<details><summary>Índice de sprints cerrados</summary>

- **Sprint 1** — MVP vertical
- **Sprint 1.5** — Modelo de proyecto + caché
- **Sprint 2** — Multi-provider + estrategias
- **Sprint 3** — Quality Gate "duro" + post de marca
- **Sprint 4** — Consistencia de personaje
- **Sprint 4.5** — Interacción AI-in-the-Loop: checkpoint de keyframe
- **Sprint 4.6** — Checkpoint de casting / look-dev
- **Sprint 5** — Producción mínima
- **Sprint 5.5** — Capa de skills
- **Sprint 6** — Audio: voz en off
- **Sprint 6.5** — Artefactos tomables a mano + nombres semánticos
- **Sprint 6.6** — La escena compone planos
- **Sprint 6.7** — Export bundle para edición humana
- **Sprint 6.8** — Guion completo
- **Sprint 6.9** — Diseño sonoro: SFX + ambiente
- **Sprint 6.11** — Perfiles de calidad + escenas en paralelo
- **Sprint 6.10** — Frame por plano + cortes cortos
- **Sprint 6.12** — Edición autónoma: describe + movis + mcp-video
- **Sprint 6.13** — Veo explícito + perfiles dinámicos en UI
- **Sprint 6.14** — Storyboard centrado en la historia: UX humano-first
- **Sprint 6.15** — Prompt derivado de la narrativa: compilable + sincronizable
- **Sprint 6.16** — El plano como artefacto audiovisual: gramática + Block
- **Sprint 6.17** — Coherencia de planos + flujo guiado + casting artefacto
- **Sprint 6.18** — Keyframe por Google + acciones masivas
- **Sprint 6.19** — Split storyboard/render + visibilidad de costos
- **Sprint 6.20** — Endurecimiento post-review Sprint 1
- **Sprint 6.21** — Endurecimiento del flujo keyframes/UI
- **Sprint 6.22** — `render
- **Sprint 6.23** — Cerrar el ciclo guion→spec: voz + routing satisfacible
- **Sprint 6.24** — Backend de voz seleccionable: ElevenLabs / Kokoro
- **Sprint 6.25** — Cinta de planos pixel-real
- **Sprint 6.26** — Animatic de poses frontera
- **Sprint 6.27** — El Studio en etapas: Casting / Encuadres / Animatic
- **Sprint 6.28** — Gramática de cobertura + palancas de calidad
- **Sprint 6.29** — Ingeniería de contexto
- **Sprint 6.30** — La edición entra al flujo
- **Sprint 6.31** — Juicio del movimiento y corte humano
- **Sprint 6.32** — El motor que SÍ llega al servidor
- **Sprint 6.33** — Orden interno: el contrato del plano y la disciplina de costo
- **Sprint 6.34** — El recorrido de ejecución: voz que no estira el film + checkpoints honestos
- **Sprint 6.35** — El libro mayor de costos
- **Sprint 6.36** — La superficie se sincroniza con el motor
- **Sprint 6.37** — El frontend se vuelve Svelte de verdad

</details>

---

## Activo / futuro

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
