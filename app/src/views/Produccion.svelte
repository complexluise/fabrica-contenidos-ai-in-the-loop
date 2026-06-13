<script>
  import { onMount } from "svelte";
  import { get, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus, PIPELINE_ORDER } from "../lib/studio.svelte.js";
  // D-088: costos movidos a Costos.svelte (una verdad, un lugar).
  // loadCosts ya no vive aca.
  import { jobState, findLiveJob } from "../lib/jobs.svelte.js";
  import JobLog from "../components/JobLog.svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import WarnStrip from "../components/WarnStrip.svelte";

  let { slug } = $props();
  // D-081: un jobState por trabajo — el ciclo busy/log/err vive UNA vez en lib.
  const jobs = { render: jobState(), export: jobState() };
  let active = $state("render");  // de cual job se muestra el registro
  let cur = $derived(jobs[active]);
  let running = $derived(jobs.render.busy ? "render" : jobs.export.busy ? "export" : "");
  let err = $derived(jobs.render.err || jobs.export.err);
  // T2.6.14: el default del perfil viene del server (D-076, sin hardcodear acá).
  let profile = $state("");
  let concurrency = $state(3);
  let profiles = $state([]);     // cargados desde /api/profiles
  let profilesErr = $state("");  // sin perfiles no hay costo visible -> no se gasta

  let st = $derived(studio.status);
  let hasFal = $derived(!!st?.keys?.fal_key);
  let renderDone = $derived(!!st?.render?.done);
  let exportDone = $derived(!!st?.export?.done);
  let finalUrl = $derived(st?.render?.final_url || null);
  // D-080: "elegir" no existe mas — la verdad es el stage del motor.
  let ready = $derived(st ? PIPELINE_ORDER.indexOf(st.stage) > PIPELINE_ORDER.indexOf("encuadres") : false);
  let selectedProfile = $derived(profiles.find(p => p.key === profile) ?? null);

  const SPEEDS = [
    { value: 1, label: "Uno a la vez", desc: "Mas seguro, menor costo si falla algo a mitad." },
    { value: 3, label: "Normal",       desc: "3 planos en paralelo. Buen balance." },
    { value: 5, label: "Rapido",       desc: "5 en paralelo. Termina antes pero usa mas cuota." },
  ];

  // colores por perfil definidos en routing.yaml -> _meta.color
  const COLOR_MAP = {
    green:  { bg: "#dcfce7", fg: "#166534" },
    yellow: { bg: "#fef3c7", fg: "#92400e" },
    blue:   { bg: "#dbeafe", fg: "#1e40af" },
    orange: { bg: "#ffedd5", fg: "#9a3412" },
    teal:   { bg: "#ccfbf1", fg: "#115e59" },
    cyan:   { bg: "#cffafe", fg: "#155e75" },
    gray:   { bg: "#f3f4f6", fg: "#374151" },
  };

  function badgeStyle(color) {
    const c = COLOR_MAP[color] ?? COLOR_MAP.gray;
    return `background:${c.bg};color:${c.fg}`;
  }

  onMount(async () => {
    try {
      profiles = await get("/api/profiles");
      // T2.6.16: SIN fallback hardcodeado — si no hay perfiles, no se renderiza
      // (el costo tiene que estar visible antes del boton que gasta, D-052).
      if (!profiles.length) profilesErr = "El servidor no devolvió perfiles. Revisá config/routing.yaml.";
      if (!profiles.find((p) => p.key === profile)) {
        profile = profiles.find((p) => p.default)?.key ?? profiles[0]?.key ?? "";
      }
    } catch (e) {
      profiles = [];
      profilesErr = humanError(e);
    }
    // T2.6.9: F5 a mitad de un render/export -> re-engancharse al job vivo
    // (en vez de mostrar la UI ociosa y dejar pagar dos veces).
    for (const kind of ["render", "export"]) {
      const live = await findLiveJob([kind], slug);
      if (live) {
        active = kind;
        jobs[kind].attach(live.id, { onDone: async () => { await refreshStatus(); } });
      }
    }
  });

  function run(kind) {
    active = kind;
    const body = kind === "render" ? { profile, concurrency } : undefined;
    jobs[kind].run(`/api/projects/${slug}/${kind}`, {
      body,
      onDone: async () => {
        await refreshStatus();
      },
    });
  }
</script>

<ViewHeader eyebrow="Paso 6 · la IA ejecuta" title="Producir">
  Ya elegiste todo. Ahora la maquina arma el video plano a plano
    (<span title="corte de referencia, no el definitivo">rough cut</span>) y prepara
    el paquete para quien edita.
</ViewHeader>

{#if !ready && !renderDone}
  <WarnStrip actionLabel="Ir a Encuadres" onaction={() => goTo("encuadres")}>
    <b>Te faltan elecciones.</b> Confirmá los encuadres de cada escena antes de renderizar.
  </WarnStrip>
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
        {#if jobs.render.status && jobs.render.status !== "done"}
          <span class="badge {jobs.render.busy ? 'warn' : 'red'}">{jobs.render.status}</span>
        {/if}
        <button class="machine" onclick={() => run("render")}
                disabled={!!running || !hasFal || !profile}
                title={profile ? "" : "Sin perfiles no hay costo visible: no se renderiza"}>
          {running === "render" ? "Renderizando…" : renderDone ? "Re-renderizar" : "Armar el video"}
        </button>
      </div>
    </div>

    <!-- Selector de perfil dinamico -->
    <div class="profile-section">
      <div class="section-label eyebrow">Perfil de generacion</div>
      {#if profilesErr}
        <p class="error" style="font-size:13px">{profilesErr}</p>
      {:else if profiles.length === 0}
        <p class="muted" style="font-size:13px">Cargando perfiles…</p>
      {:else}
        <div class="profile-row">
          {#each profiles as p}
            <button
              class="profile-opt"
              class:active={profile === p.key}
              disabled={!!running}
              onclick={() => (profile = p.key)}
            >
              <div class="profile-top">
                <span class="profile-label">{p.label}</span>
                <span class="profile-badge" style={badgeStyle(p.color)}>{p.badge}</span>
              </div>
              <span class="profile-desc">{p.desc}</span>
              {#if p.providers?.length}
                <span class="profile-providers">{p.providers.join(" + ")}</span>
              {/if}
            </button>
          {/each}
        </div>
      {/if}

      {#if selectedProfile}
        <p class="selected-hint muted">
          Usando <b>{selectedProfile.label}</b>
          {#if selectedProfile.providers?.length}
            — provider: <code>{selectedProfile.providers.join(", ")}</code>
          {/if}
        </p>
      {/if}
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
        <h3>Armar el paquete de edicion</h3>
        <p class="muted">Videos, voces, subtitulos y guion en <code>projects/{slug}/export/</code>.</p>
      </div>
      <div class="step-act">
        {#if jobs.export.status && jobs.export.status !== "done"}
          <span class="badge {jobs.export.busy ? 'warn' : 'red'}">{jobs.export.status}</span>
        {/if}
        <button onclick={() => run("export")} disabled={!!running || !renderDone}>
          {running === "export" ? "Empaquetando…" : exportDone ? "Re-armar paquete" : "Armar paquete"}
        </button>
      </div>
    </div>
    {#if !renderDone}<p class="hint muted">Disponible despues de armar el video.</p>{/if}
    {#if exportDone}
      <p class="ok-line">✓ Paquete listo. Esta en disco, dentro del proyecto.</p>
    {/if}
  </section>
</div>

{#if err}<p class="error">{err}</p>{/if}

<JobLog log={cur.log} />

<style>


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

  /* --- perfil --- */
  .profile-section { margin-top: 14px; }
  .section-label { margin-bottom: 8px; font-size: 11px; color: var(--ink-soft); }
  .profile-row { display: flex; gap: 10px; flex-wrap: wrap; }
  .profile-opt {
    flex: 1; min-width: 160px; max-width: 260px;
    display: flex; flex-direction: column; gap: 4px;
    padding: 11px 13px; border-radius: var(--r); border: 2px solid var(--line);
    background: var(--paper); text-align: left; cursor: pointer;
    box-shadow: none; transition: border-color .15s, background .15s;
  }
  .profile-opt:hover:not(:disabled) { border-color: var(--blue); background: var(--blue-wash); }
  .profile-opt.active { border-color: var(--blue); background: var(--blue-wash); }
  .profile-opt:disabled { opacity: 0.5; cursor: default; }
  .profile-top { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
  .profile-label { font-weight: 700; font-size: 14px; color: var(--ink); }
  .profile-badge {
    font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
    padding: 2px 7px; border-radius: 99px;
  }
  .profile-desc { font-size: 12px; color: var(--ink-soft); line-height: 1.4; }
  .profile-providers { font-size: 11px; color: var(--ink-soft); font-family: var(--font-mono); margin-top: 2px; }
  .selected-hint { font-size: 12px; margin-top: 8px; }

  /* --- velocidad --- */
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


</style>
