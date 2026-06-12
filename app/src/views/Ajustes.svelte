<script>
  import { onMount } from "svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import { get, put, humanError } from "../lib/api.js";
  import { goTo, refreshStatus, nextStep, studio } from "../lib/studio.svelte.js";

  let status = $state({});
  let vals = $state({ fal_key: "", anthropic_api_key: "", elevenlabs_api_key: "", google_api_key: "" });
  let msg = $state("");
  let err = $state("");

  // [clave, label, requerida?, ayuda]
  const fields = [
    ["fal_key", "FAL_KEY", true, "El motor de imágenes y video (fal.ai). Sin esto no se genera nada."],
    ["google_api_key", "GOOGLE_API_KEY", false, "Opcional: camino Google sin fal — Veo (video) y Gemini (keyframes)."],
    ["anthropic_api_key", "ANTHROPIC_API_KEY", false, "Recomendada: clasifica escenas, evalúa candidatos y nombra archivos."],
    ["elevenlabs_api_key", "ELEVENLABS_API_KEY", false, "Opcional: voz en off."],
  ];

  onMount(async () => {
    try { status = await get("/api/settings"); } catch (e) { err = humanError(e); }
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
  {#if msg}<span class="ok-msg">✓ {msg}</span>{/if}
  {#if next && next.tab !== "ajustes"}
    <button class="ghost" onclick={() => goTo(next.tab)}>Siguiente: {next.label} →</button>
  {/if}
</div>
{#if err}<p class="error">{err}</p>{/if}

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
</style>
