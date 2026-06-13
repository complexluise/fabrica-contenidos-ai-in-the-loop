<script>
  import { onMount } from "svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import { get, put, humanError } from "../lib/api.js";
  import { goTo, refreshStatus, nextStep, studio } from "../lib/studio.svelte.js";

  let status = $state({});
  let vals = $state({ fal_key: "", anthropic_api_key: "", elevenlabs_api_key: "", google_api_key: "" });
  let msg = $state("");
  let err = $state("");

  // Ajustes operativos del studio (D-092)
  let studioCfg = $state({ max_concurrency: 2 });
  let studioMsg = $state("");
  let studioErr = $state("");

  // [clave, label, requerida?, ayuda]
  const fields = [
    ["fal_key", "FAL_KEY", true, "El motor de imágenes y video (fal.ai). Sin esto no se genera nada."],
    ["google_api_key", "GOOGLE_API_KEY", false, "Opcional: camino Google sin fal — Veo (video) y Gemini (keyframes)."],
    ["anthropic_api_key", "ANTHROPIC_API_KEY", false, "Recomendada: clasifica escenas, evalúa candidatos y nombra archivos."],
    ["elevenlabs_api_key", "ELEVENLABS_API_KEY", false, "Opcional: voz en off."],
  ];

  onMount(async () => {
    try { status = await get("/api/settings"); } catch (e) { err = humanError(e); }
    try { studioCfg = await get("/api/studio-settings"); } catch (e) { /* no bloquea */ }
  });

  async function save() {
    err = ""; msg = "";
    const body = {};
    for (const k in vals) if (vals[k]) body[k] = vals[k];
    try {
      status = await put("/api/settings", body);
      vals = { fal_key: "", anthropic_api_key: "", elevenlabs_api_key: "", google_api_key: "" };
      msg = "Guardado en tu .env local.";
      await refreshStatus();
    } catch (e) {
      err = humanError(e);
    }
  }

  async function saveStudio() {
    studioErr = ""; studioMsg = "";
    try {
      studioCfg = await put("/api/studio-settings", { max_concurrency: Number(studioCfg.max_concurrency) });
      studioMsg = "Guardado.";
    } catch (e) {
      studioErr = humanError(e);
    }
  }

  let next = $derived(nextStep(studio.status));
</script>

<ViewHeader eyebrow="Configuración · setup" title="Configuración">
  Tus claves de API. Se guardan en un archivo <code>.env</code> <b>local</b> — nunca salen de tu máquina.
    Dejá un campo vacío para no cambiarlo.
</ViewHeader>

<div class="fields">
  {#each fields as [key, label, required, help]}
    <div class="field card" class:missing={required && !status[key]}>
      <div class="field-h">
        <span class="lbl mono">{label}</span>
        {#if required}<span class="badge red">requerida</span>{/if}
        <span class="badge {status[key] ? 'ok' : 'no'}">{status[key] ? "configurada" : "falta"}</span>
      </div>
      <input id={key} type="password" placeholder="••••••••••••" bind:value={vals[key]} autocomplete="off" />
      <small class="muted">{help}</small>
    </div>
  {/each}
</div>

<div class="bar">
  <button class="primary" onclick={save}>Guardar claves</button>
  {#if msg}<span class="ok-msg">&#10003; {msg}</span>{/if}
  {#if next && next.tab !== "ajustes"}
    <button class="ghost" onclick={() => goTo(next.tab)}>Siguiente: {next.label} -&gt;</button>
  {/if}
</div>
{#if err}<p class="error">{err}</p>{/if}

<hr class="sep" />

<section class="studio-section">
  <h2 class="section-title">Motor de generacion</h2>
  <p class="muted section-desc">
    Cuantos trabajos de generacion corren en paralelo. Los que superan el limite
    quedan en cola y arrancan cuando hay cupo.
  </p>

  <div class="field card concurrency-card">
    <div class="field-h">
      <span class="lbl">Jobs en paralelo</span>
      <span class="badge gray">max_concurrency</span>
    </div>
    <div class="concurrency-row">
      <input
        id="max_concurrency"
        type="number"
        min={studioCfg.max_concurrency_min ?? 1}
        max={studioCfg.max_concurrency_max ?? 16}
        bind:value={studioCfg.max_concurrency}
        class="concurrency-input"
      />
      <span class="concurrency-hint muted">
        {#if studioCfg.max_concurrency === 1}
          1 job a la vez — mas predecible, menos rafaga de API
        {:else if studioCfg.max_concurrency <= 2}
          2 en paralelo — balance entre velocidad y costo (recomendado)
        {:else}
          {studioCfg.max_concurrency} en paralelo — mayor throughput, mas llamadas simultaneas
        {/if}
      </span>
    </div>
    <small class="muted">Rango: {studioCfg.max_concurrency_min ?? 1}–{studioCfg.max_concurrency_max ?? 16}. Se aplica a los proximos trabajos (los que ya corren terminan normal).</small>
  </div>

  <div class="bar">
    <button class="primary" onclick={saveStudio}>Guardar ajustes del motor</button>
    {#if studioMsg}<span class="ok-msg">&#10003; {studioMsg}</span>{/if}
  </div>
  {#if studioErr}<p class="error">{studioErr}</p>{/if}
</section>

<style>

  .fields { display: flex; flex-direction: column; gap: 14px; max-width: 580px; }
  .field { padding: 16px 18px; }
  .field.missing { border-color: var(--red); }
  .field-h { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
  .lbl { font-size: 14px; font-weight: 700; color: var(--ink); }
  .field input { width: 100%; font-family: var(--font-mono); }
  .field small { display: block; margin-top: 7px; }

  .bar { margin-top: 22px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .ok-msg { color: var(--ok); font-weight: 600; }

  .sep { border: none; border-top: 1px solid var(--border); margin: 32px 0 24px; max-width: 580px; }

  .studio-section { max-width: 580px; }
  .section-title { font-size: 16px; font-weight: 700; margin: 0 0 6px; }
  .section-desc { margin: 0 0 16px; }

  .concurrency-card { max-width: 580px; }
  .concurrency-row { display: flex; align-items: center; gap: 16px; }
  .concurrency-input {
    width: 80px;
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    padding: 6px 8px;
  }
  .concurrency-hint { font-size: 13px; }

  .badge.gray { background: var(--muted, #888); color: #fff; }
</style>
