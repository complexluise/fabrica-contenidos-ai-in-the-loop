<script>
  import { get } from "../lib/api.js";

  let { slug } = $props();
  let data = $state(null);
  let error = $state("");
  let open = $state(new Set()); // ids de escena expandidos
  let showChars = $state(false);

  $effect(() => {
    if (!slug) return;
    data = null;
    error = "";
    open = new Set();
    showChars = false;
    get(`/api/projects/${slug}`)
      .then((d) => {
        data = d;
        if (d.scenes.length) open = new Set([d.scenes[0].id]); // la primera abierta
      })
      .catch((e) => (error = String(e)));
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
    <h1>{data.title}</h1>
    <div class="meta">
      <span class="pill">{data.style}</span>
      <span class="pill">{data.format}</span>
      <span class="pill">~{total.toFixed(0)}s</span>
      <span class="pill">{data.scenes.length} escenas</span>
    </div>
  </header>

  {#if data.brief}
    <section class="card">
      <h3>Sinopsis</h3>
      <p class="brief">{data.brief}</p>
    </section>
  {/if}

  {#if data.characters.length}
    <section class="card">
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
    <h3>Guion</h3>
    <div class="spacer"></div>
    <button onclick={allOpen}>Expandir todo</button>
    <button onclick={allClosed}>Colapsar todo</button>
  </div>

  {#each data.scenes as s}
    <section class="scene" class:open={open.has(s.id)}>
      <button class="shead" onclick={() => toggle(s.id)}>
        <span class="chev" class:open={open.has(s.id)}>▶</span>
        <span class="sid">{s.id}</span>
        {#if s.beat}<span class="beat">{s.beat}</span>{/if}
        <span class="summary">{s.shots.length} plano{s.shots.length === 1 ? "" : "s"} · {dur(s).toFixed(0)}s · {s.class}</span>
        {#if s.characters.length}
          <span class="who">{s.characters.join(", ")}</span>
        {/if}
      </button>

      {#if open.has(s.id)}
        <div class="sbody">
          <p class="desc"><span class="tag">qué pasa</span> {s.prompt}</p>
          {#each s.shots as sh, i}
            <div class="shot">
              <div class="shot-h">
                <span class="ptag">Plano {i + 1}</span>
                <span class="muted">{sh.duration_s}s</span>
                <i class="framing">{sh.framing || "plano base"}</i>
              </div>
              {#if sh.voiceover}<div class="vo">🎙️ “{sh.voiceover}”</div>{/if}
              {#if sh.caption}<div class="cap">▭ {sh.caption}</div>{/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/each}
{:else}
  <p class="muted">Cargando…</p>
{/if}

<style>
  .head { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  .head h1 { margin: 0; }
  .meta { display: flex; gap: 6px; }
  .pill { background: var(--panel2); border: 1px solid var(--border); border-radius: 20px; padding: 2px 10px; font-size: 12px; color: var(--muted); }

  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 6px 16px 14px; margin: 14px 0; }
  .card h3 { margin: 12px 0 6px; }
  .brief { color: var(--muted); max-width: 72ch; margin: 0 0 4px; }

  .chead { display: flex; align-items: center; gap: 10px; width: 100%; background: transparent; border: none; padding: 8px 0; text-align: left; }
  .chead h3 { margin: 0; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { background: var(--accent); color: #fff; border-radius: 6px; padding: 1px 9px; font-size: 12px; }
  .cbody { padding: 4px 0 6px; }
  .char { padding: 8px 0; border-top: 1px solid var(--border); }
  .char p { margin: 4px 0 0; max-width: 72ch; }
  .ref { font-size: 12px; color: var(--muted); }

  .toolbar { display: flex; align-items: center; gap: 8px; margin: 22px 0 8px; }
  .toolbar h3 { margin: 0; }
  .spacer { flex: 1; }
  .toolbar button { font-size: 13px; padding: 5px 10px; }

  .scene { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; margin: 8px 0; overflow: hidden; }
  .scene.open { border-color: var(--accent); }
  .shead { display: flex; align-items: center; gap: 12px; width: 100%; background: transparent; border: none; padding: 14px 16px; text-align: left; }
  .shead:hover { background: var(--panel2); }
  .sid { font-weight: 700; color: var(--accent2); }
  .beat { background: var(--panel2); border-radius: 6px; padding: 1px 9px; font-size: 12px; }
  .summary { color: var(--muted); font-size: 13px; }
  .who { margin-left: auto; color: var(--muted); font-size: 12px; }
  .chev { display: inline-block; transition: transform 0.15s; color: var(--muted); font-size: 11px; }
  .chev.open { transform: rotate(90deg); }

  .sbody { padding: 4px 18px 16px; border-top: 1px solid var(--border); }
  .desc { color: #cdd3df; max-width: 80ch; line-height: 1.5; }
  .tag { background: var(--warn); color: #fff; border-radius: 5px; padding: 1px 7px; font-size: 11px; font-weight: 700; margin-right: 6px; text-transform: uppercase; }
  .shot { padding: 10px 0; border-top: 1px dashed var(--border); }
  .shot-h { display: flex; align-items: center; gap: 10px; }
  .ptag { background: var(--accent); color: #fff; border-radius: 5px; padding: 1px 8px; font-size: 12px; font-weight: 700; }
  .framing { color: var(--text); }
  .vo { margin-top: 6px; color: #fc9; }
  .cap { margin-top: 4px; color: var(--accent2); font-size: 13px; }
  .muted { color: var(--muted); }
  .error { color: var(--bad); }
</style>
