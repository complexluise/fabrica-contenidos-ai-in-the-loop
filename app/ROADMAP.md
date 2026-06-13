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

## Fase 3 — Paralelo entre jobs

**Objetivo:** varias generaciones a la vez sin reventar la API ni la máquina.

### Acceptance Criteria
- [ ] AC1 — Se pueden encolar varios jobs y corren **en paralelo** hasta un límite (semáforo) configurable en Ajustes.
- [x] AC2 — El dashboard muestra **todos** los jobs activos con su progreso. ([D-083])

### Tasks
- [ ] T3.1 — Semáforo de concurrencia en el job manager + setting `max_concurrency`.
- [x] T3.2 — Dashboard de jobs: **dock siempre visible** en el sidebar (descubrimiento por poll
  de `/api/jobs` + progreso por SSE por job; reusa `attachJob`/multi-consumer de D-082). Clic en
  un job → su proyecto + pestaña. ([D-083])

> **Parcial:** AC2/T3.2 cerrados ([D-083], 2026-06-12); build de UI limpio. **Pendiente AC1/T3.1**
> (semáforo de concurrencia): el dock MUESTRA lo que corre; limitar cuántos corren es backend aparte.
> Hoy el guard 409 (D-082) ya impide el mismo job duplicado.

---

## Fase 4 — Después (diferido)

- [ ] Planos **concurrentes dentro de un render** (toca `run_project`: `gather` con cap).
- [ ] Envoltorio **desktop** (Tauri) para un ícono clickeable, si se quiere.
- [ ] Reanudar jobs tras reinicio (persistir estado; hoy en memoria, el caché hace barato re-disparar).

---

_Leyenda: 🔬 = lleva test. Lo no marcado se valida con smoke (levantar el server / abrir pantalla)._
