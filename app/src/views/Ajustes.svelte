<script>
  import { onMount } from "svelte";
  import { get, put } from "../lib/api.js";

  let status = $state({});
  let vals = $state({ fal_key: "", anthropic_api_key: "", elevenlabs_api_key: "" });
  let msg = $state("");

  const fields = [
    ["fal_key", "FAL_KEY", "Requerida — keyframes y video (fal.ai)"],
    ["anthropic_api_key", "ANTHROPIC_API_KEY", "Recomendada — clasificador, gate, naming"],
    ["elevenlabs_api_key", "ELEVENLABS_API_KEY", "Opcional — voz en off"],
  ];

  onMount(async () => { status = await get("/api/settings"); });

  async function save() {
    const body = {};
    for (const k in vals) if (vals[k]) body[k] = vals[k];
    status = await put("/api/settings", body);
    vals = { fal_key: "", anthropic_api_key: "", elevenlabs_api_key: "" };
    msg = "Guardado.";
  }
</script>

<h2>Ajustes · API keys</h2>
<p class="muted">Se guardan en <code>.env</code> local. Dejá un campo vacío para no cambiarlo.</p>

{#each fields as [key, label, help]}
  <div class="field">
    <label for={key}>
      {label}
      <span class="badge {status[key] ? 'ok' : 'no'}">{status[key] ? "configurada" : "falta"}</span>
    </label>
    <input id={key} type="password" placeholder="••••••••" bind:value={vals[key]} autocomplete="off" />
    <small class="muted">{help}</small>
  </div>
{/each}

<div class="bar">
  <button class="primary" onclick={save}>Guardar</button>
  {#if msg}<span class="muted">{msg}</span>{/if}
</div>

<style>
  .muted { color: var(--muted); }
  code { background: var(--panel2); padding: 1px 6px; border-radius: 4px; }
  .field { margin: 16px 0; max-width: 520px; }
  .field label { display: flex; align-items: center; gap: 10px; font-weight: 600; margin-bottom: 6px; }
  .field input { width: 100%; }
  .field small { display: block; margin-top: 4px; }
  .badge { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; text-transform: uppercase; }
  .badge.ok { background: var(--ok); color: #fff; }
  .badge.no { background: var(--border); color: var(--muted); }
  .bar { margin-top: 18px; display: flex; align-items: center; gap: 12px; }
</style>
