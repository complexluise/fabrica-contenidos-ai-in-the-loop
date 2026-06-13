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

## Estado

### Cerrado (histórico)

Fases 1–2.6 **cerradas**: MVP del loop en UI → entrada por import → gestión de proyectos →
hardening post-auditoría. Detalle completo en
[`../docs/roadmap/app-historico.md`](../docs/roadmap/app-historico.md).

<details><summary>Índice de fases cerradas</summary>

- **Fase 1** — MVP: el loop completo en UI
- **Fase 1.5** — UX para recién llegados
- **Fase 2** — Entrada desde la app: importar → storyboard editable
- **Fase 2.5** — Gestión de proyectos y UX del bucle
- **Fase 2.6** — Hardening post-auditoría del frontend

</details>

---

## Activo / futuro

## Fase 3 — Paralelo entre jobs  ✅ CERRADA

**Objetivo:** varias generaciones a la vez sin reventar la API ni la máquina.

### Acceptance Criteria
- [x] AC1 — Se pueden encolar varios jobs y corren **en paralelo** hasta un límite (semáforo) configurable en Ajustes. ([D-092])
- [x] AC2 — El dashboard muestra **todos** los jobs activos con su progreso. ([D-083])

### Tasks
- [x] T3.1 — Semáforo de concurrencia en el job manager + setting `max_concurrency`. ([D-092])
- [x] T3.2 — Dashboard de jobs: **dock siempre visible** en el sidebar (descubrimiento por poll
  de `/api/jobs` + progreso por SSE por job; reusa `attachJob`/multi-consumer de D-082). Clic en
  un job → su proyecto + pestaña. ([D-083])

> **Cerrada** (2026-06-13): AC2/T3.2 con [D-083] (2026-06-12); AC1/T3.1 con [D-092] (2026-06-13,
> Ciclo 2 de 3). El semáforo (`asyncio.Semaphore(max_concurrency)`, default 2, rango 1–16) vive en
> el `JobManager`: el gate va en `run()` ANTES de RUNNING, así un job en cola es QUEUED **visible**
> (lo muestra el dock) y **cuenta para el guard 409** — encola, no rechaza. `max_concurrency`
> persiste en `config/studio.yaml` (config operativa, separada de `.env`/secretos y de
> `routing.yaml`/pipeline) y se ajusta desde Ajustes vía `GET/PUT /api/studio-settings`. Hot-swap
> no estricto (aplica a los próximos jobs; trade-off consciente para local mono-usuario). NO toca
> `RenderBody.concurrency` (planos intra-render, Fase 4).

---

## Ciclo 3 — Pantalla de jobs + sección "Herramientas" del sidebar + Costos a página propia  ✅ CERRADO

> Trabajo NUEVO, no parte del AC original de Fase 3 (ese era el dock de activos + el semáforo, ya
> cerrados). Es el **Ciclo 3 de 3** del plan abierto en [D-090] (Ciclo 1 = persistencia, hecho;
> Ciclo 2 = semáforo, [D-092], hecho). ADR: [D-091].

- [x] Pantalla de **Jobs** (`views/Jobs.svelte`) que lee `GET /api/jobs/history` (paginado, ya
  existe por [D-090]) + activos del monitor global + detalle/log al click (`GET /api/jobs/{id}`,
  cae a SQLite para terminados): qué generé, cuándo, cuánto tardó, por qué falló. ([D-091])
- [x] El plano histórico vive en una pantalla dedicada; el **dock de [D-083] se mantiene** (lo
  vivo de un vistazo). **Revisa D-083**, no lo reemplaza: dock = glance, pantalla = historial +
  detalle + log. ([D-091])
- [x] Sección **"Herramientas"** en el foot del sidebar (Configuración + Jobs + Costos), FUERA de
  la espina del bucle (honra [D-086]/[D-087]); lista `TOOLS` separada de STAGES/PIPELINE_ORDER. ([D-091])
- [x] **Costos a página propia** (`views/Costos.svelte`); se quita el panel de Producción, queda un
  link "Ver costos ->" (una verdad, un lugar — [D-088]). ([D-091])

> **Cerrado** (2026-06-13) con [D-091]. Con esto el plan entero de "los jobs ganan historia"
> (abierto en [D-090]) queda **completo**: Ciclo 1 = persistencia ([D-090]), Ciclo 2 = semáforo
> ([D-092]), Ciclo 3 = pantalla/sidebar/costos ([D-091]). Sin endpoints nuevos (todo el contrato
> ya existía). Verifier: PASA CON RESERVAS (cosméticas, ya corregidas).
>
> **Refinación del smoke** (2026-06-13, [D-093]): el historial se ahogaba en micro-iteraciones.
> Se agregó `scope` ('batch'|'item') a los jobs (persistir todo, ocultar las micro por defecto);
> `GET /api/jobs/history` acepta `?kind=`/`?scope=`/`?include_micro=` y la pantalla de Jobs estrena
> filtro por tipo + toggle "mostrar micro-iteraciones" (default OFF). Polish de UI sin arquitectura
> (sidebar scrolleable, iconos de Herramientas consistentes, quitada la barra "Ver costos" de
> Producción que duplicaba la página de Costos — [D-088]).

---

## Fase 4 — Después (diferido)

- [ ] Planos **concurrentes dentro de un render** (toca `run_project`: `gather` con cap).
- [ ] Envoltorio **desktop** (Tauri) para un ícono clickeable, si se quiere.
- [~] Reanudar jobs tras reinicio. **Parcial** ([D-090], 2026-06-13): los jobs ya **persisten** en
  SQLite (`out/telemetry.sqlite`, tablas `jobs`/`job_events`) y el historial sobrevive al reinicio;
  al boot, los huérfanos queued/running se marcan `failed` (rompe el deadlock del guard 409). Falta lo
  de **reanudar** el trabajo interrumpido en sí (hoy se marca failed, no se retoma; el caché hace
  barato re-disparar). Era el **Ciclo 1 de 3** (persistencia); el semáforo (Ciclo 2, [D-092]) y la
  pantalla/sidebar de historial (Ciclo 3, [D-091]) ya están cerrados — el plan de jobs está completo,
  salvo este ítem de **reanudar** (que sigue diferido).

---

_Leyenda: 🔬 = lleva test. Lo no marcado se valida con smoke (levantar el server / abrir pantalla)._
