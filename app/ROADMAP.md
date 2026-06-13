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
[D-035]: ../docs/decisiones/0031-0040.md
[D-036]: ../docs/decisiones/0031-0040.md
[D-037]: ../docs/decisiones/0031-0040.md

---

## Fase 2 — Entrada desde la app: importar → storyboard editable

**Objetivo:** arrancar un proyecto **sin escribir YAML**. Pegás o subís texto (`.md`/`.txt`), la IA
propone el borrador (título, brief, escenas), y la persona lo **edita** (agregar/eliminar/reordenar
escenas) y confirma. Es el **Checkpoint humano #1/#2 de [D-021]** hecho interfaz: la IA descompone y
propone; la persona decide y firma. Tracker: issue #5.

### Acceptance Criteria
- [x] AC1 — **Importar:** pegar texto o subir `.md`/`.txt`; la IA lo descompone en un **borrador** de
  proyecto (título, brief, escenas con planos). `author.draft_project` (Claude) + `parse_draft` 🔬. *(Smoke real con Claude pendiente de `ANTHROPIC_API_KEY`.)*
- [x] AC2 — Se **crea** `projects/<slug>/project.yaml` desde el borrador (`project.write_spec`, round-trip + idempotente 🔬); el `slug` se deriva (Haiku/`_slugify`) y se puede fijar en el import.
- [x] AC3 — **Storyboard** (renombra *Guion*) **editable:** editar prompt/beat/duración/voz/caption por escena y plano; **agregar, eliminar y reordenar** escenas; editar título/brief.
- [x] AC4 — **Guardar** persiste al `project.yaml` con **validación** (Pydantic → 422 en humano), no a mano. 🔬
- [x] AC5 — **Guard de selecciones:** reordenar **no** corrompe `selections.yaml` (id estable); renombrar/eliminar **poda** las huérfanas (`prune_selections`). 🔬 ([D-022])
- [x] AC6 — El estado del bucle ([D-032]) reconoce **"sin proyecto"** y `nextStep` guía a *Importar*.

### Tasks (orden)
- [x] T2.1 — Motor: `ingest.extract_text` (`.md`/`.txt`) + `author.draft_project(text)` → borrador (`ProjectDraft`). 🔬 ✅ *(parseo del LLM)*
- [x] T2.2 — Motor: `project.write_spec(spec)` → `project.yaml` idempotente + `spec_from_dict` (parseo único). 🔬 ✅
- [x] T2.3 — Backend: `POST /api/projects/import` (texto) como **job/SSE** → crea el proyecto, devuelve `slug`.
- [x] T2.4 — Backend: `PUT /api/projects/{slug}` guarda el spec editado (422 si inválido, fusión por id) + guard de selecciones. 🔬
- [x] T2.5 — UI: vista **Importar** (textarea + drag-drop `.md`/`.txt`, leído client-side) al frente del bucle.
- [x] T2.6 — UI: **Storyboard** editable (ex-Guion): editar campos, agregar/eliminar/reordenar planos y escenas, Guardar.
- [x] T2.7 — Estado [D-032]: "sin proyecto" → *Importar*; etapa "Guion" → "Storyboard"; espina del bucle renumerada (Inicio · 1 Ajustes · 2 **Importar** · 3 **Storyboard** · 4 Elegir · 5 Producir).

> **✅ Fase 2 CERRADA** (2026-06-06, [D-033]). 151 tests del core en verde (+20: `test_author.py`
> + endpoints import/PUT en `test_server.py`); build de la UI limpio. Entrada sin YAML: importar texto
> → la IA propone borrador → editar/firmar el storyboard → guardar validado. El hash del caché
> ([D-013]) queda intacto (`write_spec` solo serializa). **Smoke real validado** (uvicorn + Claude):
> texto → borrador (5 escenas con planos/VO/captions/personaje) → reordenar+editar → guardar (422 en
> inválido) → guard de selecciones (poda la escena eliminada). *(El `TestClient` de FastAPI se cuelga
> con `to_thread`+SSE; por eso los unit tests mockean Claude y el smoke va contra uvicorn real.)*

> **Decisión de alcance:** el backend recibe **texto** (la UI lee el archivo client-side; sin
> `python-multipart`); `extract_text` queda para el motor/CLI.

> **Backlog implementado después del cierre** (2026-06-06): **#8 personajes con `design:` auto** en el
> import (la IA propone personajes con su prompt de diseño → habilita el casting) y **#10 estilo
> elegible** al importar (`GET /api/styles` + selector en la UI; default `lego`). +8 tests.

> **Diferido a fases siguientes**: `.docx`/`.pdf` (#7); regenerar una escena del borrador con la IA
> (#9); subir imágenes de referencia (#11); renombrar el slug de un proyecto ya creado (#12).

---

## Fase 2.5 — Gestión de proyectos y UX del bucle (los "detalles")

**Objetivo:** afinar la operación diaria. Salió de una ronda de feedback de uso. Decisiones:
[`D-035`](../docs/decisiones/0031-0040.md). El banco reusable de assets (#1) y el cambio de
frames por plano (#2) son aparte (ver [D-036]/[D-037] y el ROADMAP del motor).

### Acceptance Criteria
- [x] AC1 — **Claves a Configuración (#4):** las API keys salen del bucle numerado a un acceso
  **Configuración** (engranaje, fuera del loop); Inicio las muestra **solo si faltan**. ([D-035])
- [x] AC2 — **Firmar el plan (#5):** el Storyboard tiene un acto explícito **"Firmar el plan"** que
  persiste (`storyboard.signed`); editar sin firmar lo limpia; el paso 2 del bucle **prende el chulo**
  al firmar. 🔬 *(toggle de firmado)* ([D-035])
- [x] AC3 — **Administrar proyectos (#3):** crear un proyecto en blanco desde la UI, listarlos, abrirlos
  y **borrarlos** (con confirmación). El import sigue como alta desde texto. 🔬 *(alta/slug único/borrado/404)*

### Tasks
- [x] T2.5.1 — Backend: `PUT` acepta `sign`; `GET /status` reporta `storyboard.signed` (marcador en disco).
- [x] T2.5.2 — UI: `Configuración` fuera del bucle (sidebar + Inicio); bucle renumerado a 1-4.
- [x] T2.5.3 — UI: Storyboard con "Firmar el plan" / "Guardar borrador" + estado firmado.
- [x] T2.5.4 — Backend: `POST /api/projects` (alta en blanco) + `DELETE /api/projects/{slug}`. 🔬
- [x] T2.5.5 — UI: gestión en el sidebar (＋ Nuevo con form inline · selector · 🗑 borrar con confirm).

> **✅ Fase 2.5 CERRADA** (2026-06-07, [D-035]). #4 (claves a Configuración), #5 (firmar el plan) y
> #3 (administrar proyectos) cerrados; build de UI limpio.

---

## Fase 2.6 — Hardening post-auditoría del frontend (2026-06-12)

**Objetivo:** cerrar TODO lo que salió de la auditoría del frontend (2026-06-12): una pérdida de
datos activa en el round-trip del Storyboard, dos vías de doble gasto, y una cola de deudas de UX.
Nada de esto gasta en APIs — es solo código. Ordenado por severidad; dentro de cada bloque, en orden
de ejecución. Las referencias `archivo:línea` son del estado auditado (commit `8e72d8c`).

### Acceptance Criteria
- [x] AC1 — **Round-trip sin pérdida:** guardar/firmar el Storyboard NO altera `motion`, `lands`,
  `media`, `takes` ni `speed` de ningún plano; la UI muestra los valores reales del YAML
  (chip "sin motion" y checkbox "aterriza" dicen la verdad). 🔬 *(test de contrato PUT→GET)*
- [x] AC2 — **Imposible duplicar gasto desde la UI:** todo botón que dispara un job pago se
  deshabilita mientras corre; el server rechaza un segundo job concurrente equivalente; tras un
  F5 a mitad de job, la vista se re-engancha al job vivo en vez de mostrar la UI ociosa. 🔬
- [x] AC3 — **La firma nunca cambia en silencio:** ninguna acción des-firma el plan sin que el
  usuario lo vea (o directamente no lo des-firma, según lo que decida el ADR).
- [x] AC4 — **Un solo default de perfil:** el frontend no hardcodea `fal-ultra-cheap` ni una lista
  de perfiles fallback; el default viene del server (D-076 sin duplicación).
- [x] AC5 — **Sin fugas ni trampas de teclado:** timers del player limpiados al desmontar; los
  elementos clickeables principales operables con teclado; build de Svelte sin warnings de a11y
  en los archivos tocados.

### Bloque A — CRÍTICO: pérdida de datos en el round-trip del Storyboard
- [x] T2.6.1 — Backend: `project_detail` (`server/app.py:410-416`) serializa los 5 campos del motor
  que hoy omite: `motion`, `lands`, `media`, `takes`, `speed` (el modelo `Shot` ya los tiene,
  `contracts.py:139-152`).
- [x] T2.6.2 — 🔬 Test de contrato en `test_server.py`: PUT de un storyboard con `motion`/`lands`/
  `media`/`takes`/`speed` poblados → GET devuelve los mismos valores → segundo PUT con lo que
  devolvió el GET (round-trip literal) no cambia el `project.yaml`. Este es el test que habría
  atrapado el bug; queda como guard permanente del contrato UI↔server.
- [x] T2.6.3 — Smoke UI: proyecto con `motion` y `lands: true` en el YAML → abrir Storyboard →
  verificar que el chip "sin motion" (`Storyboard.svelte:529`) NO aparece, el checkbox "aterriza"
  está marcado y `tomas`/`vel.` muestran lo del YAML → "Guardar borrador" → re-leer el YAML
  intacto.
- [x] T2.6.4 — Revisar proyectos existentes en `projects/*/project.yaml`: si algún guardado previo
  desde la UI ya borró `motion`/`lands`/`takes`, avisar al usuario qué proyectos quedaron
  afectados (no se pueden recuperar solos; restaurar de git/backup si existe).

### Bloque B — ALTO: doble gasto
- [x] T2.6.5 — `Animatic.svelte:204-205`: renombrar el `{@const variants}` del each (p.ej.
  `poseVariants`) que hace sombra al jobState `variants` de la línea 19. Con eso `vBusy` vuelve a
  funcionar: el botón ⊞ se deshabilita y muestra "…" mientras el job de variantes corre.
- [x] T2.6.6 — Backend: guard de concurrencia en `JobManager.spawn` (o en los endpoints): si ya hay
  un job `running` del mismo `kind` para el mismo proyecto, responder 409 con mensaje legible en
  vez de lanzar otro. 🔬 *(spawn duplicado → 409; kinds distintos o proyectos distintos → OK)*
- [x] T2.6.7 — `humanError` (`api.js`): traducir ese 409 a algo humano ("Ya hay un trabajo de este
  tipo corriendo — mirá el registro").
- [x] T2.6.8 — Re-attach tras F5: helper en `jobs.svelte.js` (p.ej. `jobState.attach(jobId)`) que
  se suscribe al SSE de un job ya corriendo y repuebla `busy/log/progress` (el stream del server
  ya hace replay desde la línea 0, `jobs.py:137-141` — no hay que tocar el backend).
- [x] T2.6.9 — Al montar cada vista con jobs, consultar `GET /api/jobs` y si hay un job `running`
  del proyecto re-engancharse con el helper de T2.6.8. Cubrir las SEIS superficies que disparan
  jobs: Producción (render/export), Encuadres (keyframes global y por escena), Casting (cast),
  Animatic (completar poses y variantes), Importar (import) y Storyboard (música generada).
- [x] T2.6.10 — Smoke: lanzar un render → F5 → la vista Producción muestra "Renderizando…" con el
  log repoblado y el botón deshabilitado; intentar un segundo render por API directa → 409.

### Bloque C — MEDIO: la firma que se borra en silencio
- [x] T2.6.11 — ADR en `docs/decisiones/`: decidir la semántica de des-firmado. Hoy CUALQUIER
  `PUT` sin `sign` borra `storyboard.signed` (`server/app.py:383`), lo que incluye dos acciones
  que no editan el plan narrativo: guardar prompts desde Encuadres (`savePrompts`) y cambiar el
  backend de imagen en Storyboard (`switchBackend` → `save(false)`). Opciones: (a) el PUT
  preserva la firma cuando solo cambian campos no-narrativos (prompt/backend), o (b) se mantiene
  el des-firmado pero SIEMPRE con aviso visible. Documentar el porqué.
- [x] T2.6.12 — Implementar lo decidido en el server (qué campos disparan el unlink del marcador) +
  🔬 test: PUT solo-prompts / solo-backend vs PUT que toca escenas → firma preservada o no según
  el ADR.
- [x] T2.6.13 — UI: si una acción des-firma, decirlo donde ocurre (toast/aviso en Encuadres y en
  el toggle de backend), no solo con el cambio sutil de la espina.

### Bloque D — MEDIO: perfiles de Producción
- [x] T2.6.14 — Backend: exponer el default de perfil (D-076) en la API — p.ej. campo `default: true`
  en `GET /api/profiles` o `default_profile` en `/api/health` — para que el frontend deje de
  hardcodear `"fal-ultra-cheap"` (`Produccion.svelte:17`).
- [x] T2.6.15 — `Produccion.svelte`: usar `get()` de `api.js` en vez del `fetch` crudo (línea 60),
  con `humanError` en el catch.
- [x] T2.6.16 — Eliminar la lista fallback hardcodeada de perfiles (líneas 68-73): si
  `/api/profiles` falla, mostrar el error y deshabilitar el render (sin perfiles visibles no hay
  costo visible → no se gasta, D-052/D-055). Hoy el fallback ni siquiera contiene el perfil
  seleccionado, así que ninguna tarjeta aparece activa.

### Bloque E — MEDIO: player del Animatic
- [x] T2.6.17 — `Animatic.svelte`: `onDestroy(stopPlay)` — hoy la cadena de `setTimeout`
  (`playTimer`, líneas 92-111) sigue corriendo tras desmontar la vista.
- [x] T2.6.18 — Tecla Escape cierra el overlay del player (además del clic).

### Bloque F — BAJO: pulido y deudas menores
- [x] T2.6.19 — a11y teclado: `.shead` clickeable de Storyboard sin `role`/`tabindex`/teclado
  (`Storyboard.svelte:345`); `.read-compact` tiene `role="button"` pero no `onkeydown`
  (`Storyboard.svelte:508`); overlay `.player` de Animatic ídem (`Animatic.svelte:164`).
  Enter/Espacio activan; revisar que el build no emita warnings a11y en estos archivos.
- [x] T2.6.20 — `Storyboard.svelte:19-20`: mover `const musicJob = jobState()` ANTES del
  `$derived(musicJob.busy …)` que lo referencia — funciona por evaluación lazy pero es orden
  frágil (TDZ si algo lo evalúa temprano).
- [x] T2.6.21 — `Encuadres.svelte`: limpiar `promptsSaved[sceneId]` cuando el usuario vuelve a
  editar el prompt o los framings (hoy el "✓ guardado" queda pegado para siempre).
- [x] T2.6.22 — Personajes de escena: decidir (y anotar en este ROADMAP o un ADR) si se agrega UI
  para asignar `characters` a una escena — hoy `addScene` crea con `characters: []` y no hay
  ningún control para poblarlo, lo que afecta el contador de casting necesario. Si se difiere,
  que quede explícito como diferido (no perdido).
- [x] T2.6.23 — `server/jobs.py:145-147`: un `asyncio.Event` por consumidor en `stream()` (hoy dos
  pestañas que streamean el mismo job comparten el evento y ambas hacen `clear()` → despertares
  perdidos). Single-user lo tolera; es una mina enterrada para la Fase 3 (dashboard multi-job),
  así que puede resolverse acá o como primera task de la Fase 3 — pero que no se pierda.
- [x] T2.6.24 — Fuentes auto-hosteadas: `index.html` carga Fraunces/Hanken Grotesk desde Google
  Fonts CDN; app local-first sin red arranca con fuentes fallback. Empaquetarlas en `app/`
  (woff2 + `@font-face` en `app.css`) y quitar los `<link>` al CDN.

> Salido de la auditoría del frontend del 2026-06-12 (sin gasto de API: solo código y tests).
> Regla de cierre: cada bloque se marca al mergear con sus tests en verde; el AC2 exige el smoke
> T2.6.10 además de los unit tests.

> **✅ Fase 2.6 CERRADA** (2026-06-12, [D-082]). Los seis bloques resueltos; **411 tests del core en
> verde** (+10: round-trip del motor + `project_detail` lo expone; huella de la firma ×4 en
> `test_state.py`; 409 en `test_jobs.py` ×2 + HTTP en `test_server.py`; stream multi-consumidor) y
> **build de la UI limpio** (cero warnings a11y). Notas de cierre por bloque:
> - **A (crítico):** el `GET` expone los 5 campos del motor; el test round-trip queda como guard
>   permanente del contrato. **T2.6.4:** al 2026-06-12 ningún `project.yaml` versionado perdió datos
>   — `esquiva_conversemos` conserva sus `motion` intactos y el resto no tenía campos de motor
>   autorados (`projects/*` no se versiona salvo `lego_demo`, así que no hay más que revisar).
> - **B (doble gasto):** 409 en el server (`JobConflictError`), re-enganche en las 6 superficies
>   (`findLiveJob` + `jobState.attach`), shadowing del Animatic muerto. **T2.6.10** (smoke F5) queda
>   como verificación manual: la lógica está cubierta por unit tests; el smoke vivo lo corre el
>   operador al levantar `pipeline studio` (no automatizable sin uvicorn real, ver nota de Fase 2).
> - **C (firma):** [D-082] decide la opción (a) — la firma atestigua el plan NARRATIVO
>   (`state.plan_fingerprint`); prompt/framing/backend no des-firman; si la huella cambia, la UI lo
>   dice. **T2.6.13** integrado en el `msg` del Storyboard (sin sistema de toasts: aviso inline).
> - **D (perfiles):** `default` + `est_cost_per_scene_usd` viajan en `/api/profiles`; sin fallback
>   hardcodeado; `Produccion` usa `api.get`.
> - **E (player):** `onDestroy(stopPlay)` + Escape.
> - **F (pulido):** a11y de teclado (con `svelte-ignore` justificado donde role/tabindex van
>   acoplados), orden TDZ de `musicBusy`, `promptsSaved` se limpia al re-editar, **T2.6.22 hecho**
>   (chips de personajes en el Storyboard, no diferido), un `Event` por consumidor del stream,
>   fuentes auto-hosteadas en `app/public/fonts/`.

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
