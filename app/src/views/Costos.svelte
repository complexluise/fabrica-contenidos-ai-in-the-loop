<script>
  // Pagina de Costos (D-088: una verdad, un lugar).
  // El panel que estaba en Produccion.svelte se movio aca.
  // Consume GET /api/costs (D-079, ya existe).
  import { onMount } from "svelte";
  import { get, humanError } from "../lib/api.js";
  import ViewHeader from "../components/ViewHeader.svelte";

  let costs = $state(null);
  let err = $state("");
  let loading = $state(false);
  // Filtros opcionales (days / project)
  let days = $state("");        // "" = sin filtro (todo el historial)
  let project = $state("");     // "" = sin filtro (todos los proyectos)

  async function load() {
    loading = true; err = "";
    try {
      let url = "/api/costs";
      const params = [];
      if (days && Number(days) > 0) params.push(`days=${Number(days)}`);
      if (project.trim()) params.push(`project=${encodeURIComponent(project.trim())}`);
      if (params.length) url += "?" + params.join("&");
      costs = await get(url);
    } catch (e) {
      err = humanError(e);
      costs = null;
    } finally {
      loading = false;
    }
  }

  function fmt(n) {
    if (n == null || isNaN(n)) return "$0";
    const s = Number(n).toFixed(4).replace(/\.?0+$/, "");
    return "$" + (s || "0");
  }

  onMount(load);
</script>

<ViewHeader eyebrow="Herramientas · gastos" title="Costos">
  Cuanto se ha gastado en este studio — video, imagenes, SFX y voz.
  Fuente: <span title="out/telemetry.sqlite (D-079)">el libro mayor</span>.
</ViewHeader>

<div class="filters card">
  <label class="filter-label" for="days-input">Ultimos N dias</label>
  <input id="days-input" class="filter-input" type="number" min="1" placeholder="todos"
         bind:value={days} />
  <label class="filter-label" for="proj-input">Proyecto</label>
  <input id="proj-input" class="filter-input" type="text" placeholder="todos"
         bind:value={project} />
  <button class="primary small" onclick={load} disabled={loading}>
    {loading ? "Cargando..." : "Filtrar"}
  </button>
</div>

{#if err}
  <p class="error">{err}</p>
{:else if costs == null && loading}
  <p class="muted">Cargando costos...</p>
{:else if costs == null}
  <p class="muted">Sin datos todavia. Los costos aparecen despues de la primera generacion.</p>
{:else if costs.scenes === 0}
  <p class="muted">Sin escenas generadas en este periodo. Los costos apareceran despues de la primera generacion.</p>
{:else}

  <div class="summary">
    <div class="big-card card">
      <span class="eyebrow">Total gastado</span>
      <span class="total-num">{fmt(costs.total_usd)}</span>
      <span class="scenes-sub">{costs.scenes} escena{costs.scenes === 1 ? "" : "s"} generada{costs.scenes === 1 ? "" : "s"}</span>
    </div>

    <div class="breakdown card">
      <span class="eyebrow">Por tipo</span>
      <div class="bd-rows">
        <div class="bd-row">
          <span class="bd-label">Video</span>
          <span class="bd-val mono">{fmt(costs.breakdown?.video_usd)}</span>
        </div>
        <div class="bd-row">
          <span class="bd-label">Imagenes (keyframes)</span>
          <span class="bd-val mono">{fmt(costs.breakdown?.keyframe_usd)}</span>
        </div>
        <div class="bd-row">
          <span class="bd-label">SFX / ambiente</span>
          <span class="bd-val mono">{fmt(costs.breakdown?.sfx_usd)}</span>
        </div>
        <div class="bd-row">
          <span class="bd-label">Voz (TTS)</span>
          <span class="bd-val mono">{fmt(costs.breakdown?.tts_usd)}</span>
        </div>
      </div>
    </div>
  </div>

  {#if costs.by_project && Object.keys(costs.by_project).length > 0}
    <section class="by-proj">
      <h2 class="sec-h">Por proyecto</h2>
      <div class="proj-list">
        {#each Object.entries(costs.by_project).sort(([,a],[,b]) => b - a) as [slug, usd]}
          <div class="proj-row card">
            <span class="proj-slug mono">{slug}</span>
            <span class="proj-val mono">{fmt(usd)}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}
{/if}

<style>
  .filters {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 12px 16px; margin-bottom: 22px; max-width: 640px;
  }
  .filter-label { font-size: 13px; font-weight: 600; color: var(--ink-soft); }
  .filter-input { width: 120px; font-size: 13px; }

  .summary { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; max-width: 640px; margin-bottom: 28px; }
  @media (max-width: 580px) { .summary { grid-template-columns: 1fr; } }

  .big-card { padding: 22px 24px; display: flex; flex-direction: column; gap: 4px; }
  .total-num { font-family: var(--font-mono); font-size: 36px; font-weight: 700; color: var(--ink); }
  .scenes-sub { font-size: 12.5px; color: var(--ink-soft); }

  .breakdown { padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; }
  .bd-rows { display: flex; flex-direction: column; gap: 7px; }
  .bd-row { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px dashed var(--line); padding-bottom: 5px; }
  .bd-row:last-child { border-bottom: none; padding-bottom: 0; }
  .bd-label { font-size: 13.5px; color: var(--ink-2); }
  .bd-val { font-size: 14px; font-weight: 700; }

  .sec-h { font-size: 15px; font-weight: 700; margin: 0 0 12px; }
  .by-proj { max-width: 480px; }
  .proj-list { display: flex; flex-direction: column; gap: 6px; }
  .proj-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 9px 14px;
  }
  .proj-slug { font-size: 13.5px; color: var(--ink); }
  .proj-val { font-size: 14px; font-weight: 700; color: var(--ink); }
</style>
