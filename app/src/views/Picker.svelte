<script>
  import { get, post, runJob } from "../lib/api.js";

  let { slug } = $props();
  let cand = $state({ keyframes: {}, cast: {} });
  let kfPicks = $state({}); // escena -> índice
  let castPicks = $state({}); // personaje -> índice
  let busy = $state("");
  let msg = $state("");
  let n = $state(4);

  async function load() {
    cand = await get(`/api/projects/${slug}/candidates`);
  }
  $effect(() => {
    if (slug) { kfPicks = {}; castPicks = {}; msg = ""; load(); }
  });

  function generate(kind) {
    busy = kind;
    msg = `Generando ${kind}…`;
    runJob(`/api/projects/${slug}/${kind}?n=${n}`, {
      onLine: (l) => (msg = l),
      onDone: async (status) => {
        busy = "";
        msg = status === "done" ? "Listo. Elegí abajo." : `Terminó: ${status}`;
        await load();
      },
      onError: () => { busy = ""; msg = "Error al generar."; },
    });
  }

  async function savePicks() {
    if (Object.keys(kfPicks).length)
      await post(`/api/projects/${slug}/pick`, { picks: kfPicks });
    if (Object.keys(castPicks).length)
      await post(`/api/projects/${slug}/pick-cast`, { picks: castPicks });
    msg = "Selección guardada.";
  }

  const entries = (o) => Object.entries(o || {});
</script>

<div class="bar">
  <label>N <input type="number" min="1" max="8" bind:value={n} style="width:60px" /></label>
  <button onclick={() => generate("keyframes")} disabled={!!busy}>Generar keyframes</button>
  <button onclick={() => generate("cast")} disabled={!!busy}>Generar casting</button>
  <div class="spacer"></div>
  <button class="primary" onclick={savePicks} disabled={!!busy}>Guardar selección</button>
</div>
{#if msg}<p class="msg mono">{msg}</p>{/if}

{#if entries(cand.cast).length}
  <h2>Casting</h2>
  {#each entries(cand.cast) as [name, urls]}
    <div class="group">
      <h3>{name} {#if castPicks[name] != null}<span class="chosen">elegido: {castPicks[name]}</span>{/if}</h3>
      <div class="grid">
        {#each urls as url, i}
          <button class="cand" class:sel={castPicks[name] === i} onclick={() => (castPicks = { ...castPicks, [name]: i })}>
            <img src={url} alt="{name} {i}" />
            <span class="idx">{i}</span>
          </button>
        {/each}
      </div>
    </div>
  {/each}
{/if}

{#if entries(cand.keyframes).length}
  <h2>Keyframes</h2>
  {#each entries(cand.keyframes) as [scene, urls]}
    <div class="group">
      <h3>{scene} {#if kfPicks[scene] != null}<span class="chosen">elegido: {kfPicks[scene]}</span>{/if}</h3>
      <div class="grid">
        {#each urls as url, i}
          <button class="cand" class:sel={kfPicks[scene] === i} onclick={() => (kfPicks = { ...kfPicks, [scene]: i })}>
            <img src={url} alt="{scene} {i}" />
            <span class="idx">{i}</span>
          </button>
        {/each}
      </div>
    </div>
  {/each}
{:else if !entries(cand.cast).length}
  <p class="muted">No hay candidatos todavía. Generá keyframes o casting arriba.</p>
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
  .spacer { flex: 1; }
  .msg { color: var(--muted); font-size: 13px; }
  .group { margin: 16px 0; }
  .group h3 { color: var(--accent2); margin: 0 0 8px; }
  .chosen { color: var(--ok); font-size: 13px; font-weight: 400; margin-left: 8px; }
  .grid { display: flex; flex-wrap: wrap; gap: 10px; }
  .cand { position: relative; padding: 4px; border-radius: 8px; background: var(--panel); }
  .cand img { display: block; max-width: 200px; max-height: 200px; border-radius: 4px; }
  .cand.sel { outline: 3px solid var(--ok); border-color: var(--ok); }
  .idx { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.6); color: #fff; border-radius: 4px; padding: 0 6px; font-size: 12px; }
  .muted { color: var(--muted); }
</style>
