<script>
  // Pantalla de Jobs: activos (del monitor global) + historial paginado de SQLite.
  // Los jobs activos se toman del store `jobsMonitor` (D-083, ya pollea vivo).
  // El historial usa GET /api/jobs/history (Ciclo 1, paginado limit/offset).
  // Click en un job terminado -> GET /api/jobs/{id} para ver log completo.
  import { onMount } from "svelte";
  import { jobsMonitor } from "../lib/jobs.svelte.js";
  import { studio, setSlug, goTo } from "../lib/studio.svelte.js";
  import { get, humanError } from "../lib/api.js";
  import ViewHeader from "../components/ViewHeader.svelte";
  import JobLog from "../components/JobLog.svelte";

  // --- historial ---
  const PAGE = 30;
  let history = $state([]);
  let historyErr = $state("");
  let loading = $state(false);
  let offset = $state(0);
  let hasMore = $state(false);

  // --- detalle de un job terminado ---
  let selected = $state(null);   // { id, kind, project, status, logs, error, ... }
  let detailErr = $state("");
  let detailLoading = $state(false);

  // jobs activos del monitor global
  let active = $derived(Object.values(jobsMonitor.items));

  // etiqueta humana por kind (mismo mapa que JobsDock)
  const KIND = {
    import:        { label: "Importando",  tab: "importar" },
    cast:          { label: "Casting",     tab: "casting" },
    keyframes:     { label: "Encuadres",   tab: "encuadres" },
    shots:         { label: "Planos",      tab: "encuadres" },
    animatic:      { label: "Animatic",    tab: "animatic" },
    pose_variants: { label: "Variantes",   tab: "animatic" },
    render:        { label: "Render",      tab: "producir" },
    export:        { label: "Paquete",     tab: "producir" },
    music:         { label: "Musica",      tab: "storyboard" },
  };
  const kindLabel = (k) => (KIND[k] || { label: k }).label;

  function fmtTs(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleString("es-AR", {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function durSec(row) {
    if (!row.started_at || !row.ended_at) return null;
    const s = Math.round(row.ended_at - row.started_at);
    if (s < 60) return `${s}s`;
    return `${Math.floor(s / 60)}m ${s % 60}s`;
  }

  async function loadHistory(reset = false) {
    if (loading) return;
    if (reset) { offset = 0; history = []; }
    loading = true; historyErr = "";
    try {
      const rows = await get(`/api/jobs/history?limit=${PAGE}&offset=${offset}`);
      history = reset ? rows : [...history, ...rows];
      hasMore = rows.length === PAGE;
      offset += rows.length;
    } catch (e) {
      historyErr = humanError(e);
    } finally {
      loading = false;
    }
  }

  async function showDetail(jobId) {
    if (selected?.id === jobId) { selected = null; return; }
    detailErr = ""; detailLoading = true; selected = null;
    try {
      selected = await get(`/api/jobs/${jobId}`);
    } catch (e) {
      detailErr = humanError(e);
    } finally {
      detailLoading = false;
    }
  }

  async function jumpToJob(job) {
    const base = (job.project || "").split("/")[0];
    if (base && base !== studio.slug && studio.projects.some((p) => p.slug === base)) {
      await setSlug(base);
    }
    const tab = (KIND[job.kind] || {}).tab || "inicio";
    goTo(tab);
  }

  onMount(() => loadHistory(true));
</script>

<ViewHeader eyebrow="Herramientas · trabajos" title="Jobs">
  Los trabajos activos y el historial de lo que ya termino. Hace click en un
  job terminado para ver su log completo.
</ViewHeader>

<!-- ACTIVOS -->
<section class="section">
  <h2 class="sec-h">Activos ahora <span class="count-badge">{active.length}</span></h2>

  {#if active.length === 0}
    <p class="muted empty-line">No hay trabajos corriendo en este momento.</p>
  {:else}
    <div class="job-list">
      {#each active as j (j.id)}
        <div class="job-row card active-row">
          <span class="dot pulse" class:bad={j.status !== "running" && j.status !== "queued" && j.status !== "done"}
                class:ok={j.status === "done"}></span>
          <div class="job-info">
            <span class="job-kind">{kindLabel(j.kind)}</span>
            <span class="job-proj mono">{(j.project || "").split("/")[0]}</span>
          </div>
          <span class="job-prog mono">{j.status === "done" ? "terminado" : j.status === "queued" ? "en cola..." : (j.progress || "trabajando...")}</span>
          <button class="mini go-btn" onclick={() => jumpToJob(j)} title="Ir a la vista de este job">
            ver &rarr;
          </button>
        </div>
      {/each}
    </div>
  {/if}
</section>

<!-- HISTORIAL -->
<section class="section">
  <div class="sec-head-row">
    <h2 class="sec-h">Historial</h2>
    <button class="mini" onclick={() => loadHistory(true)} disabled={loading}>
      {loading ? "Cargando..." : "Actualizar"}
    </button>
  </div>

  {#if historyErr}
    <p class="error">{historyErr}</p>
  {:else if history.length === 0 && !loading}
    <p class="muted empty-line">Sin historial todavia. Los trabajos completados apareceran aca.</p>
  {:else}
    <div class="job-list">
      {#each history as row (row.id)}
        <button
          class="job-row card hist-row"
          class:active={selected?.id === row.id}
          class:is-fail={row.status === "failed"}
          onclick={() => showDetail(row.id)}
        >
          <span class="status-dot" class:ok={row.status === "done"} class:fail={row.status === "failed"}></span>
          <div class="job-info">
            <span class="job-kind">{kindLabel(row.kind)}</span>
            <span class="job-proj mono">{(row.project || "").split("/")[0]}</span>
          </div>
          <span class="job-ts muted">{fmtTs(row.ended_at)}</span>
          {#if durSec(row)}
            <span class="job-dur mono">{durSec(row)}</span>
          {/if}
          <span class="badge {row.status === 'done' ? 'ok' : 'red'}">{row.status === 'done' ? 'listo' : 'fallo'}</span>
        </button>

        {#if selected?.id === row.id}
          <div class="detail card">
            {#if detailLoading}
              <p class="muted">Cargando detalle...</p>
            {:else if detailErr}
              <p class="error">{detailErr}</p>
            {:else if selected}
              <div class="detail-meta">
                <span><b>ID:</b> <span class="mono">{selected.id}</span></span>
                <span><b>Proyecto:</b> <span class="mono">{selected.project}</span></span>
                {#if selected.error}
                  <span class="error-line"><b>Error:</b> {selected.error}</span>
                {/if}
                {#if selected.started_at}
                  <span><b>Inicio:</b> {fmtTs(selected.started_at)}</span>
                {/if}
                {#if selected.ended_at}
                  <span><b>Fin:</b> {fmtTs(selected.ended_at)}</span>
                {/if}
                {#if durSec(selected)}
                  <span><b>Duracion:</b> {durSec(selected)}</span>
                {/if}
              </div>
              <JobLog log={selected.logs || []}
                      placeholder="Sin log guardado para este job." />
            {/if}
          </div>
        {/if}
      {/each}
    </div>

    {#if loading}
      <p class="muted loading-line">Cargando...</p>
    {:else if hasMore}
      <button class="ghost load-more" onclick={() => loadHistory(false)}>Cargar mas</button>
    {/if}
  {/if}
</section>

<style>
  .section { margin-bottom: 36px; }
  .sec-h {
    font-size: 15px; font-weight: 700; margin: 0 0 12px;
    display: flex; align-items: center; gap: 9px;
  }
  .sec-head-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .sec-head-row .sec-h { margin: 0; }
  .count-badge {
    font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: #fff;
    background: var(--blue); border-radius: 999px; min-width: 20px; height: 20px;
    display: inline-grid; place-items: center; padding: 0 6px;
  }

  .job-list { display: flex; flex-direction: column; gap: 6px; }

  /* fila base */
  .job-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-radius: var(--r);
  }

  /* fila activa (div, no boton) */
  .active-row { background: var(--paper-2); }

  /* fila de historial (boton) */
  .hist-row {
    width: 100%; text-align: left; cursor: pointer;
    background: var(--paper-2); border: 1px solid var(--line);
    box-shadow: none;
  }
  .hist-row:hover { background: var(--card); border-color: var(--line-2); box-shadow: none; }
  .hist-row.active { background: var(--card); border-color: var(--blue); box-shadow: var(--shadow); }
  .hist-row.is-fail { border-color: var(--red); }

  /* indicadores de estado */
  .dot {
    width: 10px; height: 10px; flex-shrink: 0; border-radius: 50%; background: var(--blue);
  }
  .dot.pulse { animation: j-pulse 1.4s ease-in-out infinite; }
  .dot.bad { background: var(--red); animation: none; }
  .dot.ok { background: var(--ok); animation: none; }
  @keyframes j-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

  .status-dot {
    width: 10px; height: 10px; flex-shrink: 0; border-radius: 50%;
    background: var(--line-2); border: 2px solid var(--line-2);
  }
  .status-dot.ok { background: var(--ok); border-color: var(--ok); }
  .status-dot.fail { background: var(--red); border-color: var(--red); }

  .job-info { display: flex; flex-direction: column; gap: 1px; min-width: 110px; }
  .job-kind { font-weight: 700; font-size: 13.5px; }
  .job-proj { font-size: 11px; color: var(--ink-soft); }

  .job-prog { font-size: 11.5px; color: var(--ink-soft); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .job-ts { font-size: 12px; margin-left: auto; white-space: nowrap; }
  .job-dur { font-size: 11.5px; color: var(--ink-soft); white-space: nowrap; }

  .go-btn { margin-left: auto; }

  /* detalle expandido debajo de la fila */
  .detail {
    padding: 16px 18px; margin-top: -2px;
    border-top: none; border-top-left-radius: 0; border-top-right-radius: 0;
  }
  .detail-meta {
    display: flex; flex-wrap: wrap; gap: 10px 24px;
    font-size: 13px; margin-bottom: 10px;
  }
  .error-line { color: var(--red-deep); }

  .empty-line { font-size: 14px; }
  .loading-line { margin-top: 10px; font-size: 13px; }
  .load-more { margin-top: 14px; }
</style>
