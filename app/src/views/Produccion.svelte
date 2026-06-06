<script>
  import { runJob } from "../lib/api.js";

  let { slug } = $props();
  let log = $state([]);
  let status = $state("");
  let result = $state(null);
  let running = $state("");

  function run(kind) {
    log = [];
    status = "running";
    result = null;
    running = kind;
    runJob(`/api/projects/${slug}/${kind}`, {
      onLine: (l) => (log = [...log, l]),
      onDone: (s, _id) => { status = s; running = ""; },
      onError: () => { status = "error"; running = ""; },
    });
  }
</script>

<div class="bar">
  <button class="primary" onclick={() => run("render")} disabled={!!running}>
    {running === "render" ? "Renderizando…" : "Render"}
  </button>
  <button onclick={() => run("export")} disabled={!!running}>
    {running === "export" ? "Exportando…" : "Armar paquete (export)"}
  </button>
  {#if status}<span class="status {status}">{status}</span>{/if}
</div>

<p class="hint">
  <b>Render</b> genera el video plano a plano (rough cut). <b>Export</b> arma el paquete para la
  editora en <code>projects/{slug}/export/</code>.
</p>

<div class="log mono">
  {#if log.length === 0}
    <span class="muted">El progreso aparece acá en vivo…</span>
  {:else}
    {#each log as l}<div>{l}</div>{/each}
  {/if}
</div>

<style>
  .bar { display: flex; align-items: center; gap: 10px; }
  .status { font-size: 13px; padding: 2px 10px; border-radius: 20px; text-transform: uppercase; }
  .status.done { background: var(--ok); color: #fff; }
  .status.failed, .status.error { background: var(--bad); color: #fff; }
  .status.running { background: var(--warn); color: #fff; }
  .hint { color: var(--muted); font-size: 13px; }
  code { background: var(--panel2); padding: 1px 6px; border-radius: 4px; }
  .log {
    margin-top: 12px; background: #0b0d11; border: 1px solid var(--border);
    border-radius: 10px; padding: 14px; min-height: 220px; max-height: 460px;
    overflow: auto; font-size: 13px; line-height: 1.6; white-space: pre-wrap;
  }
  .muted { color: var(--muted); }
</style>
