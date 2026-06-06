<script>
  import { runJob, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus, stepDone } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let running = $state(""); // "render" | "export" | ""
  let log = $state([]);
  let kindStatus = $state({ render: "", export: "" });
  let err = $state("");
  let showLog = $state(true);

  let st = $derived(studio.status);
  let hasFal = $derived(!!st?.keys?.fal_key);
  let renderDone = $derived(!!st?.render?.done);
  let exportDone = $derived(!!st?.export?.done);
  let finalUrl = $derived(st?.render?.final_url || null);

  // listo para renderizar = el paso "Elegir" esta hecho (lo decide el motor)
  let ready = $derived(stepDone("elegir", st));

  function run(kind) {
    log = []; err = ""; running = kind; kindStatus = { ...kindStatus, [kind]: "running" };
    runJob(`/api/projects/${slug}/${kind}`, {
      onLine: (l) => (log = [...log, l]),
      onDone: async (s) => {
        running = ""; kindStatus = { ...kindStatus, [kind]: s };
        if (s !== "done") err = `Terminó como: ${s}. Revisá el registro.`;
        await refreshStatus();
      },
      onError: (e) => { running = ""; kindStatus = { ...kindStatus, [kind]: "error" }; err = humanError(e); },
    });
  }
</script>

<header class="head">
  <div class="eyebrow">Paso 4 · la IA ejecuta</div>
  <h1>Producir</h1>
  <p class="lede">
    Ya elegiste todo. Ahora la máquina arma el video plano a plano
    (<span title="corte de referencia, no el definitivo">rough cut</span>) y prepara
    el paquete para quien edita.
  </p>
</header>

{#if !ready && !renderDone}
  <div class="warn-strip">
    <b>Te faltan elecciones.</b> Volvé a <i>Elegir</i> y confirmá los encuadres antes de renderizar.
    <button class="small" onclick={() => goTo("elegir")}>Ir a Elegir →</button>
  </div>
{/if}

<div class="steps">
  <!-- 1. Render -->
  <section class="step card" class:is-done={renderDone}>
    <div class="step-h">
      <span class="num actor-ia">{renderDone ? "✓" : "A"}</span>
      <div>
        <h3>Armar el video</h3>
        <p class="muted">Genera cada plano y los une en un corte de referencia.</p>
      </div>
      <div class="step-act">
        {#if kindStatus.render && kindStatus.render !== "done"}
          <span class="badge {kindStatus.render === 'running' ? 'warn' : 'red'}">{kindStatus.render}</span>
        {/if}
        <button class="machine" onclick={() => run("render")} disabled={!!running || !hasFal}>
          {running === "render" ? "Renderizando…" : renderDone ? "Re-renderizar" : "Armar el video"}
        </button>
      </div>
    </div>
    {#if finalUrl}
      <video class="preview" src={finalUrl} controls playsinline>
        <track kind="captions" />
      </video>
    {/if}
  </section>

  <!-- 2. Export -->
  <section class="step card" class:is-done={exportDone}>
    <div class="step-h">
      <span class="num actor-ia">{exportDone ? "✓" : "B"}</span>
      <div>
        <h3>Armar el paquete de edición</h3>
        <p class="muted">Videos, voces, subtítulos y guion en <code>projects/{slug}/export/</code>.</p>
      </div>
      <div class="step-act">
        {#if kindStatus.export && kindStatus.export !== "done"}
          <span class="badge {kindStatus.export === 'running' ? 'warn' : 'red'}">{kindStatus.export}</span>
        {/if}
        <button onclick={() => run("export")} disabled={!!running || !renderDone}>
          {running === "export" ? "Empaquetando…" : exportDone ? "Re-armar paquete" : "Armar paquete"}
        </button>
      </div>
    </div>
    {#if !renderDone}<p class="hint muted">Disponible después de armar el video.</p>{/if}
    {#if exportDone}
      <p class="ok-line">✓ Paquete listo. Está en disco, dentro del proyecto.</p>
    {/if}
  </section>
</div>

{#if err}<p class="error">{err}</p>{/if}

<div class="log-wrap">
  <button class="log-toggle eyebrow" onclick={() => (showLog = !showLog)}>
    {showLog ? "▾" : "▸"} Registro en vivo
  </button>
  {#if showLog}
    <div class="log mono">
      {#if log.length === 0}
        <span class="muted">El progreso aparece acá mientras la máquina trabaja…</span>
      {:else}
        {#each log as l}<div>{l}</div>{/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .head { margin-bottom: 18px; }
  .head h1 { margin: 5px 0 8px; }
  .lede { max-width: 58ch; color: var(--ink-2); font-size: 16px; }
  .lede span[title] { border-bottom: 1.5px dotted var(--ink-soft); cursor: help; }

  .warn-strip {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--warn-wash); border: 1.5px solid #e0c089; color: #6b4a12;
    border-radius: var(--r); padding: 12px 16px; margin-bottom: 18px;
  }
  .warn-strip button { margin-left: auto; }

  .steps { display: flex; flex-direction: column; gap: 14px; }
  .step { padding: 18px 20px; }
  .step.is-done { border-color: var(--ok); }
  .step-h { display: flex; align-items: center; gap: 14px; }
  .step-h h3 { margin: 0; }
  .step-h p { margin: 2px 0 0; font-size: 13px; }
  .num {
    width: 34px; height: 34px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center;
    font-family: var(--font-mono); font-weight: 700; border: 2px solid var(--blue); color: var(--blue-deep);
    background: var(--paper);
  }
  .step.is-done .num { background: var(--ok); border-color: var(--ok); color: #fff; }
  .step-act { margin-left: auto; display: flex; align-items: center; gap: 10px; }

  .preview { margin-top: 14px; max-width: 280px; border-radius: var(--r); border: 1px solid var(--line); background: #000; }
  .hint { font-size: 13px; margin: 10px 0 0; }
  .ok-line { color: var(--ok); margin: 12px 0 0; font-weight: 600; }

  .log-wrap { margin-top: 22px; }
  .log-toggle { background: transparent; border: none; padding: 4px 0; cursor: pointer; box-shadow: none; }
  .log-toggle:hover { color: var(--ink); box-shadow: none; }
  .log {
    margin-top: 8px; background: #211c16; color: #d8cdb8; border: 1px solid var(--line-2);
    border-radius: var(--r); padding: 14px 16px; min-height: 130px; max-height: 420px;
    overflow: auto; font-size: 12.5px; line-height: 1.65; white-space: pre-wrap;
  }
  .muted { color: var(--ink-soft); }
</style>
