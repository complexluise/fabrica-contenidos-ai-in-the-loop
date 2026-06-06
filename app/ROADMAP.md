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
- [ ] AC1 — **Pantalla de Inicio** con un **checklist de estado** del proyecto (keys · casting · keyframes elegidos · render · export) y el **siguiente paso** sugerido.
- [ ] AC2 — El sidebar **numera y ordena** el flujo (Inicio · 1 Ajustes · 2 Guion · 3 Picker · 4 Render/Export).
- [ ] AC3 — **Sin API key**, los botones de "Generar" quedan **deshabilitados** con un cartel claro ("Configurá las keys en Ajustes"); los errores se muestran **en humano**, no como traceback.
- [ ] AC4 — **CTA de siguiente paso**: tras elegir → "Siguiente: Render"; tras render → "Siguiente: Export".
- [ ] AC5 — **Sub-etiquetas en lenguaje claro** (una línea de ayuda por pantalla; traducir la jerga: keyframes = imagen base, casting = cara del personaje, rough cut = corte de referencia).

### Tasks (orden)
- [ ] T1.5.1 — Backend: `GET /api/projects/{slug}/status` (casting hecho X/Y, candidatos, escenas elegidas X/Y, run, export). 🔬 *(lógica de estado)*
- [ ] T1.5.2 — Vista **Inicio**: checklist con ✓/⬜ + botón "siguiente paso" que salta a la pestaña correcta.
- [ ] T1.5.3 — Sidebar numerado + reordenado; `setTab` compartido para navegar desde Inicio/CTA.
- [ ] T1.5.4 — Picker: deshabilitar "Generar" sin `fal_key`; banner de error en humano; CTA tras guardar.
- [ ] T1.5.5 — Render/Export: CTA "Siguiente: Export" tras render; error en humano.
- [ ] T1.5.6 — Sub-etiquetas/ayuda por pantalla (glosario corto inline).

---

## Fase 2 — Paralelo entre jobs

**Objetivo:** varias generaciones a la vez sin reventar la API ni la máquina.

### Acceptance Criteria
- [ ] AC1 — Se pueden encolar varios jobs y corren **en paralelo** hasta un límite (semáforo) configurable en Ajustes.
- [ ] AC2 — El dashboard muestra **todos** los jobs activos con su progreso.

### Tasks
- [ ] T2.1 — Semáforo de concurrencia en el job manager + setting `max_concurrency`.
- [ ] T2.2 — Dashboard de jobs (varios SSE / un stream multiplexado).

---

## Fase 3 — Después (diferido)

- [ ] Planos **concurrentes dentro de un render** (toca `run_project`: `gather` con cap).
- [ ] Envoltorio **desktop** (Tauri) para un ícono clickeable, si se quiere.
- [ ] Reanudar jobs tras reinicio (persistir estado; hoy en memoria, el caché hace barato re-disparar).

---

_Leyenda: 🔬 = lleva test. Lo no marcado se valida con smoke (levantar el server / abrir pantalla)._
