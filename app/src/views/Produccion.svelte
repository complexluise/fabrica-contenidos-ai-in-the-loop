<script>
  import { runJob, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus, stepDone } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let running = $state(""); // "render" | "export" | ""
  let log = $state([]);
  let kindStatus = $state({ render: "", export: "" });
  let err = $state("");
  let showLog = $state(true);
  let profile = $state("proto"); // "proto" | "prod"
  let concurrency = $state(3);   // 1 | 3 | 5

  let st = $derived(studio.status);
  let hasFal = $derived(!!st?.keys?.fal_key);
  let renderDone = $derived(!!st?.render?.done);
  let exportDone = $derived(!!st?.export?.done);
  let finalUrl = $derived(st?.render?.final_url || null);

  // listo para renderizar = el paso "Elegir" esta hecho (lo decide el motor)
  let ready = $derived(stepDone("elegir", st));

  const PROFILES = {
    proto: {
      label: "Prototipo",
      desc: "Un modelo, sin ensemble. Barato y rapido para validar el storyboard.",
      badge: "rapido",
    },
    prod: {
      label: "Produccion",
      desc: "Hero en ensemble (mejor de N), gate de calidad, modelos premium.",
      badge: "calidad",
    },
  };

  const SPEEDS = [
    { value: 1, label: "Uno a la vez", desc: "Mas seguro, menor costo si falla algo a mitad." },
    { value: 3, label: "Normal",       desc: "3 planos en paralelo. Buen balance." },
    { value: 5, label: "Rapido",      desc: "5 en paralelo. Termina antes pero usa mas cuota de fal." },
  ];

  function run(kind) {
    log = []; err = ""; running = kind; kindStatus = { ...kindStatus, [kind]: "running" };
    const body = kind === "render" ? { profile, concurrency } : undefined;
    runJob(`/api/projects/${slug}/${kind}`, {
      body,
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

    <!-- Selector de calidad -->
    <div class="profile-row">
      {#each Object.entries(PROFILES) as [key, p]}
        <button
          class="profile-opt"
          class:active={profile === key}
          disabled={!!running}
          onclick={() => (profile = key)}
        >
          <span class="profile-label">{p.label}</span>
          <span class="profile-badge {key}">{p.badge}</span>
          <span class="profile-desc">{p.desc}</span>
        </button>
      {/each}
    </div>

    <!-- Selector de velocidad -->
    <div class="speed-label eyebrow">Velocidad de generacion</div>
    <div class="speed-row">
      {#each SPEEDS as s}
        <button
          class="speed-opt"
          class:active={concurrency === s.value}
          disabled={!!running}
          onclick={() => (concurrency = s.value)}
          title={s.desc}
        >
          {s.label}
        </button>
      {/each}
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

  /* --- selector de perfil --- */
  .profile-row {
    display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap;
  }
  .profile-opt {
    flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 3px;
    padding: 12px 14px; border-radius: var(--r); border: 2px solid var(--line);
    background: var(--paper); text-align: left; cursor: pointer;
    box-shadow: none; transition: border-color .15s, background .15s;
  }
  .profile-opt:hover:not(:disabled) { border-color: var(--blue); background: var(--blue-wash); }
  .profile-opt.active { border-color: var(--blue); background: var(--blue-wash); }
  .profile-opt:disabled { opacity: 0.5; cursor: default; }
  .profile-label { font-weight: 700; font-size: 14px; color: var(--ink); }
  .profile-badge {
    display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase; padding: 2px 7px; border-radius: 99px; width: fit-content;
  }
  .profile-badge.proto { background: #fef3c7; color: #92400e; }
  .profile-badge.prod  { background: #dcfce7; color: #166534; }
  .profile-desc { font-size: 12px; color: var(--ink-soft); margin-top: 2px; }

  /* --- selector de velocidad --- */
  .speed-label { margin-top: 14px; margin-bottom: 6px; font-size: 11px; color: var(--ink-soft); }
  .speed-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .speed-opt {
    padding: 6px 14px; border-radius: 99px; border: 1.5px solid var(--line);
    background: var(--paper); font-size: 13px; cursor: pointer;
    transition: border-color .15s, background .15s; box-shadow: none;
  }
  .speed-opt:hover:not(:disabled) { border-color: var(--blue); background: var(--blue-wash); }
  .speed-opt.active { border-color: var(--blue); background: var(--blue-wash); font-weight: 600; color: var(--blue-deep); }
  .speed-opt:disabled { opacity: 0.5; cursor: default; }

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
