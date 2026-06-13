<script>
  // [Fase 3 / D-083] Dashboard de jobs: TODOS los activos con su progreso,
  // siempre visible en el sidebar. Clic en uno -> a su proyecto + pestaña.
  import { jobsMonitor } from "../lib/jobs.svelte.js";
  import { studio, goTo, setSlug } from "../lib/studio.svelte.js";

  // kind del server -> etiqueta humana + pestaña donde vive ese trabajo.
  const KIND = {
    import:        { label: "Importando", tab: "importar" },
    cast:          { label: "Casting",    tab: "casting" },
    keyframes:     { label: "Encuadres",  tab: "encuadres" },
    shots:         { label: "Planos",     tab: "encuadres" },
    animatic:      { label: "Animatic",   tab: "animatic" },
    pose_variants: { label: "Variantes",  tab: "animatic" },
    render:        { label: "Render",     tab: "producir" },
    export:        { label: "Paquete",    tab: "producir" },
    music:         { label: "Música",     tab: "storyboard" },
  };
  const meta = (k) => KIND[k] || { label: k, tab: "inicio" };

  let jobs = $derived(Object.values(jobsMonitor.items));

  async function open(job) {
    const base = (job.project || "").split("/")[0];
    if (base && base !== studio.slug && studio.projects.some((p) => p.slug === base)) {
      await setSlug(base);
    }
    goTo(meta(job.kind).tab);
  }
</script>

{#if jobs.length}
  <div class="dock">
    <div class="dock-h">
      <span class="eyebrow">Trabajos</span>
      <span class="count">{jobs.length}</span>
    </div>
    {#each jobs as j (j.id)}
      {@const m = meta(j.kind)}
      {@const sub = (j.project || "").split("/")[0]}
      <button class="job state-{j.status}" onclick={() => open(j)}
              title="Ir a {m.label} · {sub}">
        <span class="dot" class:done={j.status === "done"} class:bad={j.status !== "done" && j.status !== "running" && j.status !== "queued"}></span>
        <span class="job-t">
          <span class="job-top">
            <b class="job-kind">{m.label}</b>
            <span class="job-proj mono">{sub}</span>
          </span>
          <span class="job-prog">
            {#if j.status === "done"}terminado ✓
            {:else if j.status === "queued"}en cola…
            {:else}{j.progress || "trabajando…"}{/if}
          </span>
        </span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .dock {
    display: flex; flex-direction: column; gap: 6px;
    background: var(--card); border: 1px solid var(--line-2);
    border-radius: var(--r); padding: 10px;
    max-height: 38vh; overflow-y: auto;  /* muchos jobs no empujan config/leyenda */
  }
  .dock-h { display: flex; align-items: center; justify-content: space-between; }
  .count {
    font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #fff;
    background: var(--blue); border-radius: 999px; min-width: 18px; height: 18px;
    display: grid; place-items: center; padding: 0 5px;
  }
  .job {
    display: flex; align-items: center; gap: 9px; width: 100%; text-align: left;
    background: var(--paper-2); border: 1px solid var(--line);
    border-radius: var(--r-sm); padding: 7px 9px; box-shadow: none;
  }
  .job:hover { background: var(--paper); border-color: var(--line-2); box-shadow: none; }
  .job.state-done { border-color: var(--ok); }
  .dot {
    width: 9px; height: 9px; flex-shrink: 0; border-radius: 50%;
    background: var(--blue); animation: dock-pulse 1.4s ease-in-out infinite;
  }
  .dot.done { background: var(--ok); animation: none; }
  .dot.bad { background: var(--red); animation: none; }
  @keyframes dock-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  .job-t { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
  .job-top { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
  .job-kind { font-size: 12.5px; color: var(--ink); }
  .job-proj { font-size: 10.5px; color: var(--ink-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .job-prog {
    font-size: 10.5px; color: var(--ink-soft); overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
  }
</style>
