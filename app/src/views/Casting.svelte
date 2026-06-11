<script>
  // [D-061] Etapa 3 · Casting: QUIÉNES son. Una página = una decisión.
  // Extraída del Picker ("Elegir"), que mezclaba tres decisiones distintas.
  import { get, post, runJob, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus, GLOSARIO } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let cast = $state({});          // personaje -> [urls]
  let picks = $state({});         // personaje -> indice
  let busy = $state(false);
  let progress = $state("");
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
  let genBackend = $state("fal");
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);

  let castNeeded = $derived(studio.status?.casting?.needed ?? 0);
  let brokenCast = $derived(studio.status?.integrity?.casting ?? []);
  let estPerImg = $derived(studio.status?.est_cost_per_image_usd ?? 0.003);
  // Costo SIEMPRE visible antes del botón que gasta (D-052/D-055/D-061).
  let estCost = $derived(Math.max(castNeeded, 1) * n * estPerImg);

  const entries = (o) => Object.entries(o || {});
  let hasCast = $derived(entries(cast).length > 0);
  let anyPick = $derived(Object.keys(picks).length > 0);

  async function load() {
    try {
      const c = await get(`/api/projects/${slug}/candidates`);
      cast = c.cast || {};
      const fromDisk = {};
      for (const [name, selPath] of Object.entries(c.cast_selections || {})) {
        const urls = cast[name] || [];
        const filename = String(selPath).split(/[/\\]/).pop();
        const idx = urls.findIndex((url) => url.split("/").pop() === filename);
        if (idx >= 0) fromDisk[name] = idx;
      }
      picks = { ...fromDisk, ...picks };
    } catch (e) { err = humanError(e); }
  }
  $effect(() => { if (slug) { picks = {}; err = ""; saved = false; load(); } });

  function generate() {
    busy = true; err = ""; saved = false;
    progress = "Pidiéndole caras a la IA…";
    runJob(`/api/projects/${slug}/cast?n=${n}&backend=${genBackend}`, {
      onLine: (l) => (progress = l),
      onDone: async (status) => {
        busy = false;
        progress = status === "done" ? "Listo. Elegí abajo." : "";
        if (status !== "done") err = `La generación terminó como: ${status}.`;
        await load(); await refreshStatus();
      },
      onError: (e) => { busy = false; progress = ""; err = humanError(e); },
    });
  }

  async function save() {
    err = "";
    try {
      await post(`/api/projects/${slug}/pick-cast`, { picks });
      saved = true;
      await load(); await refreshStatus();
    } catch (e) { err = humanError(e); }
  }
</script>

<header class="head">
  <div class="eyebrow">Paso 3 · vos decidís</div>
  <h1>Casting</h1>
  <p class="lede">
    <span title={GLOSARIO.casting}>La cara de cada personaje, fijada una vez.</span>
    La IA <b class="b">propone</b> varias; vos <b class="r">elegís</b> la que va.
    Esa cara viaja a todos los encuadres y planos.
  </p>
</header>

{#if castNeeded === 0}
  <div class="empty card">
    <p>Este proyecto no tiene personajes con diseño de casting.</p>
    <p class="muted">Podés seguir directo a <button class="small ghost" onclick={() => goTo("encuadres")}>Encuadres →</button></p>
  </div>
{:else}
  <div class="generate card">
    <div class="gen-l">
      <div class="eyebrow" style="color:var(--blue-deep)">La IA propone</div>
      <p class="muted gen-help">Genera {n} caras candidatas por personaje. La elegida se fija como identidad.</p>
      <p class="est-line">≈ <b>${estCost.toFixed(3)}</b>
        <span class="muted">por {n} caras × {castNeeded} personaje{castNeeded === 1 ? "" : "s"} con {genBackend === "google" ? "Google" : "fal"}</span></p>
    </div>
    <div class="gen-controls">
      <div class="backend-toggle" title="Motor de imagen (D-051/D-053)">
        <span class="bt-lbl">motor</span>
        <button class="bt-opt" class:active={genBackend === "fal"} disabled={busy}
                onclick={() => (genBackend = "fal")}>fal</button>
        <button class="bt-opt" class:active={genBackend === "google"} disabled={busy || !hasGoogle}
                onclick={() => (genBackend = "google")}
                title={hasGoogle ? "Gemini imagen (sin fal)" : "Falta GOOGLE_API_KEY"}>Google</button>
      </div>
      <label class="n-lbl">opciones
        <input type="number" min="1" max="8" bind:value={n} />
      </label>
      <button class="machine cta" onclick={generate} disabled={busy || !canGen}>
        {busy ? "Generando…" : hasCast ? "Regenerar casting" : "Generar casting"}
      </button>
    </div>
  </div>

  {#if !canGen}
    <p class="note">🔒 Necesitás la clave de {genBackend === "google" ? "Google" : "fal.ai"}.
      <button class="small ghost" onclick={() => goTo("ajustes")}>Configurarla</button></p>
  {/if}

  {#if busy}<div class="progress mono"><span class="spin"></span>{progress}</div>{/if}
  {#if err}<p class="error">{err}</p>{/if}

  {#if brokenCast.length}
    <div class="warn-banner broken">
      <b>⚠ Referencias rotas.</b>
      <span>La cara de <b class="mono">{brokenCast.join(", ")}</b> ya no está en disco — regenerá el casting.</span>
    </div>
  {/if}

  {#if hasCast}
    {#each entries(cast) as [name, urls]}
      <div class="group">
        <div class="group-h">
          <b>{name}</b>
          {#if picks[name] != null}<span class="badge red">elegido · {picks[name]}</span>{/if}
        </div>
        <div class="lighttable">
          {#each urls as url, i}
            <button class="cell" class:sel={picks[name] === i}
                    onclick={() => { picks = { ...picks, [name]: i }; saved = false; }}>
              <img src={url} alt="{name} {i}" loading="lazy" />
              <span class="idx">{i}</span>
              {#if picks[name] === i}<span class="stamp">elegido</span>{/if}
            </button>
          {/each}
        </div>
      </div>
    {/each}
  {:else if !busy}
    <div class="empty card">
      <p>Todavía no hay caras para elegir.</p>
      <p class="muted">Usá <b>Generar casting</b> arriba.</p>
    </div>
  {/if}

  {#if hasCast}
    <div class="savebar">
      {#if saved}
        <span class="saved-seal">✓ Casting fijado</span>
        <button class="primary cta" onclick={() => goTo("encuadres")}>Siguiente: Encuadres →</button>
      {:else}
        <button class="primary cta" onclick={save} disabled={!anyPick}>Fijar casting</button>
        {#if !anyPick}<span class="muted">Hacé clic en la cara que va.</span>{/if}
      {/if}
    </div>
  {/if}
{/if}

<style>
  .head { margin-bottom: 18px; }
  .head h1 { margin: 5px 0 8px; }
  .lede { max-width: 56ch; color: var(--ink-2); font-size: 16px; }
  .lede .b { color: var(--blue-deep); }
  .lede .r { color: var(--red-deep); }
  .generate { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; padding: 16px 20px; margin-bottom: 14px; }
  .gen-l { flex: 1; min-width: 220px; }
  .gen-help { font-size: 13px; margin: 4px 0 0; max-width: 52ch; }
  .gen-controls { display: flex; align-items: center; gap: 9px; }
  .n-lbl { display: flex; flex-direction: column; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); gap: 3px; }
  .n-lbl input { width: 64px; font-family: var(--font-mono); }
  .backend-toggle { display: inline-flex; align-items: center; gap: 0; border: 1.5px solid var(--line-2); border-radius: 999px; overflow: hidden; }
  .bt-lbl { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); padding: 0 8px 0 11px; }
  .bt-opt { border: none; border-radius: 0; box-shadow: none; background: var(--paper); padding: 6px 12px; font-size: 13px; font-weight: 600; color: var(--ink-soft); }
  .bt-opt.active { background: var(--blue); color: #fff; }
  .bt-opt:disabled { opacity: 0.4; }
  .est-line { font-size: 12.5px; margin: 6px 0 0; }
  .est-line b { color: var(--ink); font-family: var(--font-mono); }
  .note { background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r); padding: 9px 14px; font-size: 14px; }
  .progress { display: flex; align-items: center; gap: 10px; background: var(--blue-wash); border: 1px solid #b9c2ee; color: var(--blue-deep); border-radius: var(--r); padding: 10px 14px; font-size: 13px; }
  .spin { width: 13px; height: 13px; border: 2px solid var(--blue-deep); border-right-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .warn-banner { border-radius: var(--r); padding: 10px 14px; margin-bottom: 12px; font-size: 13.5px; display: flex; flex-direction: column; gap: 4px; }
  .warn-banner.broken { background: var(--red-wash); border: 1px solid var(--red); color: var(--red-deep); }
  .warn-banner .mono { font-family: var(--font-mono); }
  .group { margin: 14px 0 22px; }
  .group-h { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 16px; }
  .lighttable { display: flex; flex-wrap: wrap; gap: 12px; background: #2a251e; border: 1px solid var(--line-2); border-radius: var(--r); padding: 14px; box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35); }
  .cell { position: relative; padding: 0; background: #1a1611; border: 2px solid transparent; border-radius: var(--r-sm); overflow: hidden; line-height: 0; box-shadow: none; transition: transform 0.1s ease, border-color 0.12s ease; }
  .cell:hover { transform: translateY(-3px) scale(1.01); border-color: rgba(255, 255, 255, 0.4); box-shadow: 0 8px 20px -6px rgba(0,0,0,0.6); }
  .cell img { display: block; max-width: 210px; max-height: 230px; }
  .cell.sel { border-color: var(--red); box-shadow: 0 0 0 3px var(--red-wash), 0 8px 22px -6px rgba(0,0,0,0.6); }
  .idx { position: absolute; top: 7px; left: 7px; background: rgba(0,0,0,0.62); color: #fff; border-radius: var(--r-sm); padding: 0 7px; font-family: var(--font-mono); font-size: 12px; }
  .stamp { position: absolute; top: 9px; right: -28px; transform: rotate(14deg); background: var(--red); color: #fff8f2; font-weight: 700; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 30px; box-shadow: 0 2px 6px rgba(0,0,0,0.4); }
  .empty { padding: 30px; text-align: center; margin-top: 16px; }
  .empty p { margin: 4px 0; }
  .savebar { position: sticky; bottom: 0; margin-top: 26px; padding: 16px 0 8px; background: linear-gradient(0deg, var(--paper) 60%, transparent); display: flex; align-items: center; gap: 14px; }
  .saved-seal { font-size: 13px; font-weight: 700; color: var(--ok); background: var(--ok-wash); border-radius: 999px; padding: 6px 14px; }
  .muted { color: var(--ink-soft); }
</style>
