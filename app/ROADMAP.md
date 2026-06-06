# ROADMAP — Studio local (app)

> Track **separado** del pipeline (ver [`../ROADMAP.md`](../ROADMAP.md) para el motor). Decisión:
> [`D-031`](../docs/decisiones/0031-0040.md). Filosofía: **local, sin auth, estado en disco** — la UI es
> el loop donde la persona decide ([D-021]). Backend **FastAPI** en `src/pipeline/server/`, UI
> **Svelte** en `app/`. La API es cáscara fina sobre `studio`/`runner`/`export` (no se reescribe el motor).

## Metodología

- **Reusar el motor, no reescribirlo.** Los endpoints llaman a las funciones que ya existen.
- **Test-first donde hay lógica pura** (job manager: estados/transiciones; mapeos de la API).
  La UI y la integración se validan con smoke (levantar el server, abrir la pantalla).
- **Un sprint a la vez**, commit al cierre, ADR antes/junto al trabajo.

---

## Fase 1 — MVP: el loop completo en UI

**Objetivo:** que el equipo trabaje **sin terminal**. Una corrida de punta a punta: abrir proyecto →
ver candidatos → **clic** para elegir → render con **progreso en vivo** → descargar el export. Jobs
de a uno (sin paralelo todavía). Ajustes para las API keys.

### Acceptance Criteria
- [x] AC1 — `pipeline studio` levanta el server local y abre `localhost` en el navegador.
- [x] AC2 — **Ajustes:** configurar las API keys desde la UI (se persisten en `.env` e invalidan el cache de `settings`).
- [x] AC3 — **Proyectos:** listar `projects/*`, abrir uno, ver sus escenas/planos (vista Guion).
- [x] AC4 — **Picker:** disparar `keyframes`/`cast`, ver la galería de N candidatos, **elegir con clic** (persiste igual que `pick`/`pick-cast`).
- [x] AC5 — **Render:** disparar `render`, ver el **progreso en vivo** (SSE) hasta el rough cut.
- [x] AC6 — **Export:** botón "armar paquete" → `export_bundle`. *(Smoke real con SSE -> done.)*

### Tasks (orden)
- [x] T1.1 — `src/pipeline/server/`: app FastAPI + `pipeline studio` (uvicorn + abre browser).
- [x] T1.2 — **Job manager** async en proceso (estados + buffer de log por job). 🔬 ✅
- [x] T1.3 — Endpoints del motor (projects, keyframes/cast/render/export -> job, jobs + SSE).
- [x] T1.4 — Endpoints de selección (`pick`/`pick-cast`).
- [x] T1.5 — **Ajustes:** `GET/PUT /settings` + invalida el `lru_cache`.
- [x] T1.6 — Sirve `/files` (imágenes de candidatos) + el build de la UI.
- [x] T1.7 — **UI Svelte** (`app/`, Vite + pnpm): Guion, Picker (galería + clic), Render/Export (progreso vivo), Ajustes; build servido por FastAPI.
- [x] T1.8 — Smoke: API con TestClient (4) + uvicorn real (health/projects + ciclo de export con SSE).

> **✅ Fase 1 CERRADA** (2026-06-05). Backend (131 tests verde, +8) + UI Svelte; `pipeline studio`
> sirve UI+API+SSE en un origen. **Pendiente:** correr el loop completo con API real (FAL) —
> generar → elegir en la galería → render con progreso → export.

---

## Fase 1.5 — UX para recién llegados (quick wins)

**Objetivo:** que alguien que abre la app **sin saber nada** entienda el flujo solo. Sale de la
auditoría de UX: hoy la app asume que ya conocés `casting → keyframes → elegir → render → export`.
No lo enseña, no lo ordena, ni te dice dónde estás.

### Acceptance Criteria
- [x] AC1 — **Pantalla de Inicio** con un **checklist de estado** del proyecto (keys · casting · keyframes elegidos · render · export) y el **siguiente paso** sugerido.
- [x] AC2 — El sidebar **numera y ordena** el flujo (Inicio · 1 Ajustes · 2 Guion · 3 **Elegir** · 4 **Producir**). *(El "Picker" pasó a llamarse Elegir y "Render/Export" a Producir — lenguaje más claro.)*
- [x] AC3 — **Sin API key**, los botones de "Generar" quedan **deshabilitados** con un cartel claro ("Configurá las keys en Ajustes"); los errores se muestran **en humano** (`humanError`), no como traceback.
- [x] AC4 — **CTA de siguiente paso**: tras elegir → "Siguiente: Producir"; tras render → "Siguiente: Export".
- [x] AC5 — **Sub-etiquetas en lenguaje claro** (una línea de ayuda por pantalla; traducir la jerga: keyframes = imagen base, casting = cara del personaje, rough cut = corte de referencia).

### Tasks (orden)
- [x] T1.5.1 — Backend: `GET /api/projects/{slug}/status` (casting hecho X/Y, candidatos, escenas elegidas X/Y, run, export). 🔬 *(creció a [D-032]: estado **derivado** del disco, fuente única; `state.compute_stage`/`derive_state`)*
- [x] T1.5.2 — Vista **Inicio**: checklist con ✓/⬜ + botón "siguiente paso" que salta a la pestaña correcta.
- [x] T1.5.3 — Sidebar numerado + reordenado (la espina del bucle); store compartido (`studio.svelte.js`) para navegar desde Inicio/CTA.
- [x] T1.5.4 — Elegir: deshabilitar "Generar" sin `fal_key`; banner de error en humano; CTA tras guardar.
- [x] T1.5.5 — Producir: CTA "Siguiente: Export" tras render; error en humano.
- [x] T1.5.6 — Sub-etiquetas/ayuda por pantalla (glosario corto inline).

> **✅ Fase 1.5 CERRADA** (2026-06-06, PR #2). UI a dos tintas (azul = la IA propone, rojo = la
> persona decide) + espina del bucle + Inicio que orienta. El estado del proyecto se **deriva** del
> disco ([D-032]), fuente única para server y front. **Pendiente:** smoke del loop completo con API real.

[D-021]: ../docs/decisiones/0021-0030.md
[D-022]: ../docs/decisiones/0021-0030.md
[D-032]: ../docs/decisiones/0031-0040.md

---

## Fase 2 — Entrada desde la app: importar → storyboard editable

**Objetivo:** arrancar un proyecto **sin escribir YAML**. Pegás o subís texto (`.md`/`.txt`), la IA
propone el borrador (título, brief, escenas), y la persona lo **edita** (agregar/eliminar/reordenar
escenas) y confirma. Es el **Checkpoint humano #1/#2 de [D-021]** hecho interfaz: la IA descompone y
propone; la persona decide y firma. Tracker: issue #5.

### Acceptance Criteria
- [ ] AC1 — **Importar:** pegar texto o subir `.md`/`.txt`; la IA lo descompone en un **borrador** de
  proyecto (título, brief, escenas con planos). Reúsa `ingest.decompose_script` + el L2 classifier.
- [ ] AC2 — Se **crea** `projects/<slug>/project.yaml` desde el borrador (nuevo escritor del spec); el
  `slug` se deriva y se puede editar.
- [ ] AC3 — **Storyboard** (renombra *Guion*) **editable:** editar prompt/beat/duración/voz/caption por
  escena y plano; **agregar, eliminar y reordenar** escenas; editar título/brief.
- [ ] AC4 — **Guardar** persiste al `project.yaml` con **validación** (Pydantic; error en humano si algo
  no cierra), no a mano.
- [ ] AC5 — **Guard de selecciones:** reordenar/renombrar escenas **no corrompe** `selections.yaml`
  ([D-022]); se re-mapea por id o se avisa.
- [ ] AC6 — El estado del bucle ([D-032]) reconoce **"sin proyecto"** y guía a *Importar*.

### Tasks (orden)
- [ ] T2.1 — Motor: `ingest.extract_text` (`.md`/`.txt`) + `author.draft_project(text)` → borrador (Pydantic). 🔬 *(parseo del LLM)*
- [ ] T2.2 — Motor: `project.write_spec(spec)` → `project.yaml` idempotente + validado. 🔬
- [ ] T2.3 — Backend: `POST /api/projects/import` (texto o archivo) como **job/SSE** → crea el proyecto, devuelve `slug`.
- [ ] T2.4 — Backend: `PUT /api/projects/{slug}` guarda el spec editado (422 si inválido) + guard de selecciones.
- [ ] T2.5 — UI: vista **Importar** (textarea + drag-drop `.md`/`.txt`) al frente del bucle.
- [ ] T2.6 — UI: **Storyboard** editable (ex-Guion): editar campos, agregar/eliminar/reordenar, Guardar.
- [ ] T2.7 — Estado [D-032]: stage `SIN_PROYECTO` → *Importar*; renombrar la etapa "Guion" a "Storyboard".

> **Diferido a fases siguientes** (acordado al cortar el alcance): `.docx`/`.pdf`; **personajes con
> `design:` auto** (habilita el casting desde el import); regenerar una escena del borrador con la IA;
> plantillas por estilo; subir imágenes de referencia; estado `BORRADOR` como guard.

---

## Fase 3 — Paralelo entre jobs

**Objetivo:** varias generaciones a la vez sin reventar la API ni la máquina.

### Acceptance Criteria
- [ ] AC1 — Se pueden encolar varios jobs y corren **en paralelo** hasta un límite (semáforo) configurable en Ajustes.
- [ ] AC2 — El dashboard muestra **todos** los jobs activos con su progreso.

### Tasks
- [ ] T3.1 — Semáforo de concurrencia en el job manager + setting `max_concurrency`.
- [ ] T3.2 — Dashboard de jobs (varios SSE / un stream multiplexado).

---

## Fase 4 — Después (diferido)

- [ ] Planos **concurrentes dentro de un render** (toca `run_project`: `gather` con cap).
- [ ] Envoltorio **desktop** (Tauri) para un ícono clickeable, si se quiere.
- [ ] Reanudar jobs tras reinicio (persistir estado; hoy en memoria, el caché hace barato re-disparar).

---

_Leyenda: 🔬 = lleva test. Lo no marcado se valida con smoke (levantar el server / abrir pantalla)._
