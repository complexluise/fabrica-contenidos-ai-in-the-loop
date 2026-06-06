<script>
  import { get, humanError } from "../lib/api.js";
  import { goTo } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let data = $state(null);
  let error = $state("");
  let open = $state(new Set()); // ids de escena expandidos
  let showChars = $state(false);

  $effect(() => {
    if (!slug) return;
    data = null; error = ""; open = new Set(); showChars = false;
    get(`/api/projects/${slug}`)
      .then((d) => {
        data = d;
        if (d.scenes.length) open = new Set([d.scenes[0].id]);
      })
      .catch((e) => (error = humanError(e)));
  });

  function toggle(id) {
    const s = new Set(open);
    s.has(id) ? s.delete(id) : s.add(id);
    open = s;
  }
  const allOpen = () => (open = new Set(data.scenes.map((s) => s.id)));
  const allClosed = () => (open = new Set());

  const dur = (s) => s.shots.reduce((a, sh) => a + (sh.duration_s || 0), 0);
  const total = $derived(data ? data.scenes.reduce((a, s) => a + dur(s), 0) : 0);
</script>

{#if error}
  <p class="error">{error}</p>
{:else if data}
  <header class="head">
    <div class="eyebrow">Paso 2 · leer</div>
    <h1>{data.title}</h1>
    <p class="lede muted">Lo que vamos a contar, escena por escena y plano por plano.</p>
    <div class="meta">
      <span class="pill">{data.style}</span>
      <span class="pill">{data.format}</span>
      <span class="pill">~{total.toFixed(0)}s</span>
      <span class="pill">{data.scenes.length} escena{data.scenes.length === 1 ? "" : "s"}</span>
    </div>
  </header>

  {#if data.brief}
    <section class="card pad">
      <h3>Sinopsis</h3>
      <p class="brief">{data.brief}</p>
    </section>
  {/if}

  {#if data.characters.length}
    <section class="card pad">
      <button class="chead" onclick={() => (showChars = !showChars)}>
        <span class="chev" class:open={showChars}>▶</span>
        <h3>Personajes ({data.characters.length})</h3>
        <div class="chips">
          {#each data.characters as c}<span class="chip">{c.name}</span>{/each}
        </div>
      </button>
      {#if showChars}
        <div class="cbody">
          {#each data.characters as c}
            <div class="char">
              <b>{c.name}</b>
              {#if c.design}<p class="muted">{c.design}</p>{/if}
              {#if c.refs.length}<p class="ref mono">ref: {c.refs.join(", ")}</p>{/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  <div class="toolbar">
    <h2>Guion</h2>
    <div class="spacer"></div>
    <button class="small ghost" onclick={allOpen}>Expandir todo</button>
    <button class="small ghost" onclick={allClosed}>Colapsar todo</button>
  </div>

  {#each data.scenes as s}
    <section class="scene" class:open={open.has(s.id)}>
      <button class="shead" onclick={() => toggle(s.id)}>
        <span class="chev" class:open={open.has(s.id)}>▶</span>
        <span class="sid">{s.id}</span>
        {#if s.beat}<span class="beat">{s.beat}</span>{/if}
        <span class="summary">{s.shots.length} plano{s.shots.length === 1 ? "" : "s"} · {dur(s).toFixed(0)}s · {s.class}</span>
        {#if s.characters.length}<span class="who">{s.characters.join(", ")}</span>{/if}
      </button>

      {#if open.has(s.id)}
        <div class="sbody">
          <p class="desc"><span class="tag">qué pasa</span> {s.prompt}</p>
          {#each s.shots as sh, i}
            <div class="shot">
              <div class="shot-h">
                <span class="ptag">Plano {i + 1}</span>
                <span class="muted mono">{sh.duration_s}s</span>
                <i class="framing">{sh.framing || "plano base"}</i>
              </div>
              {#if sh.voiceover}<div class="vo">🎙 “{sh.voiceover}”</div>{/if}
              {#if sh.caption}<div class="cap">▭ {sh.caption}</div>{/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/each}

  <div class="cta">
    <button class="primary" onclick={() => goTo("elegir")}>Siguiente: Elegir →</button>
    <span class="muted">La IA propondrá opciones y vos elegís.</span>
  </div>
{:else}
  <p class="muted">Cargando…</p>
{/if}

<style>
  .head { margin-bottom: 16px; }
  .head h1 { margin: 5px 0 6px; }
  .lede { font-size: 16px; margin: 0 0 12px; }
  .meta { display: flex; gap: 7px; flex-wrap: wrap; }

  .card.pad { padding: 6px 18px 16px; margin: 14px 0; }
  .card h3 { margin: 14px 0 6px; }
  .brief { color: var(--ink-2); max-width: 72ch; margin: 0 0 4px; }

  .chead { display: flex; align-items: center; gap: 10px; width: 100%; background: transparent; border: none; padding: 8px 0; text-align: left; box-shadow: none; }
  .chead:hover { box-shadow: none; }
  .chead h3 { margin: 0; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { background: var(--blue); color: #fff; border-radius: var(--r-sm); padding: 1px 9px; font-size: 12px; font-weight: 600; }
  .cbody { padding: 4px 0 6px; }
  .char { padding: 9px 0; border-top: 1px solid var(--line); }
  .char p { margin: 4px 0 0; max-width: 72ch; }
  .ref { font-size: 12px; color: var(--ink-soft); }

  .toolbar { display: flex; align-items: center; gap: 8px; margin: 26px 0 10px; }
  .toolbar h2 { margin: 0; }
  .spacer { flex: 1; }

  .scene { background: var(--card); border: 1.5px solid var(--line); border-radius: var(--r); margin: 9px 0; overflow: hidden; }
  .scene.open { border-color: var(--blue); }
  .shead { display: flex; align-items: center; gap: 12px; width: 100%; background: transparent; border: none; padding: 14px 16px; text-align: left; border-radius: 0; box-shadow: none; }
  .shead:hover { background: var(--paper-2); box-shadow: none; }
  .sid { font-family: var(--font-mono); font-weight: 700; color: var(--blue-deep); }
  .beat { background: var(--paper-2); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 1px 9px; font-size: 12px; }
  .summary { color: var(--ink-soft); font-size: 13px; }
  .who { margin-left: auto; color: var(--ink-soft); font-size: 12px; }
  .chev { display: inline-block; transition: transform 0.15s; color: var(--ink-soft); font-size: 11px; }
  .chev.open { transform: rotate(90deg); }

  .sbody { padding: 6px 18px 16px; border-top: 1px solid var(--line); }
  .desc { color: var(--ink); max-width: 80ch; line-height: 1.55; }
  .tag { background: var(--warn); color: #fff; border-radius: var(--r-sm); padding: 1px 8px; font-size: 11px; font-weight: 700; margin-right: 7px; text-transform: uppercase; letter-spacing: 0.04em; }
  .shot { padding: 11px 0; border-top: 1px dashed var(--line); }
  .shot-h { display: flex; align-items: center; gap: 10px; }
  .ptag { background: var(--blue); color: #fff; border-radius: var(--r-sm); padding: 1px 9px; font-size: 12px; font-weight: 700; }
  .framing { color: var(--ink); }
  .vo { margin-top: 7px; color: var(--red-deep); }
  .cap { margin-top: 5px; color: var(--blue-deep); font-size: 13px; }

  .cta { margin: 30px 0 0; display: flex; align-items: center; gap: 14px; }
  .muted { color: var(--ink-soft); }
</style>
