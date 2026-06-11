<script>
  // [D-060/D-061] Etapa 5 · Animatic: cómo FLUYE la película — en poses, ANTES
  // de pagar video. Cada plano = apertura → destino; el render interpola entre
  // ellas (en paralelo). Curación por excepción: todo viene propuesto; regenerás
  // solo la pose que no convence.
  import { get, post, del, runJob, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus, GLOSARIO } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let data = $state(null);      // { strip, total, ready, missing_poses, est_missing_cost_usd }
  let profiles = $state([]);    // para el estimado del render (costo visible, D-061)
  let busy = $state(false);
  let progress = $state("");
  let err = $state("");
  let dropping = $state("");    // "shot_id/which" en proceso de descarte

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let strip = $derived(data?.strip ?? []);
  let allReady = $derived(data && data.total > 0 && data.ready >= data.total);
  let scenes = $derived([...new Set(strip.map((e) => e.scene))]);
  let totalDur = $derived(strip.reduce((a, e) => a + (e.duration_s || 0), 0));

  // Costo visible (D-061): completar poses + estimado del render por perfil.
  let estMissing = $derived(data?.est_missing_cost_usd ?? 0);
  let cheapProfile = $derived(profiles.length
    ? profiles.reduce((a, b) => (a.est_cost_per_scene_usd <= b.est_cost_per_scene_usd ? a : b))
    : null);
  let estRender = $derived(cheapProfile ? cheapProfile.est_cost_per_scene_usd * scenes.length : null);

  const TRANS = {
    cut: { icon: "✂", title: "corte" },
    smash_cut: { icon: "⚡", title: "smash cut" },
    wipe: { icon: "▥", title: "wipe" },
    match_cut: { icon: "⇢", title: "match cut" },
    dissolve: { icon: "◐", title: "dissolve" },
  };
  const transOf = (t) => TRANS[t] || { icon: "→", title: "continuo" };

  async function load() {
    try {
      const [a, p] = await Promise.all([
        get(`/api/projects/${slug}/animatic`),
        get(`/api/profiles`).catch(() => []),
      ]);
      data = a; profiles = p || [];
    } catch (e) { err = humanError(e); }
  }
  $effect(() => { if (slug) { data = null; err = ""; load(); } });

  function generate() {
    busy = true; err = "";
    progress = "Generando las poses que faltan…";
    runJob(`/api/projects/${slug}/animatic`, {
      onLine: (l) => (progress = l),
      onDone: async (status) => {
        busy = false; progress = "";
        if (status !== "done") err = `Terminó como: ${status}.`;
        await load(); await refreshStatus();
      },
      onError: (e) => { busy = false; progress = ""; err = humanError(e); },
    });
  }

  // Curación por excepción: descartar UNA pose → "Generar" la repone (solo esa).
  async function regenPose(shotId, which) {
    dropping = `${shotId}/${which}`; err = "";
    try {
      await del(`/api/projects/${slug}/animatic/${shotId}/${which}`);
      await load();
    } catch (e) { err = humanError(e); }
    finally { dropping = ""; }
  }
</script>

<header class="head">
  <div class="eyebrow">Paso 5 · vos decidís</div>
  <h1>Animatic</h1>
  <p class="lede">
    <span title={GLOSARIO.animatic}>La película completa en poses</span>, <b class="r">antes</b> de pagar
    el video. Cada plano va de su <b>apertura</b> a su <b>destino</b>; el render interpola entre ellas.
    Si una pose no convence, descartala y regenerá — solo esa.
  </p>
</header>

{#if data}
  <div class="generate card">
    <div class="gen-l">
      <div class="eyebrow" style="color:var(--blue-deep)">La IA propone</div>
      <p class="muted gen-help">
        {data.ready}/{data.total} planos con sus dos poses ·
        {totalDur.toFixed(0)}s de película en {scenes.length} escena{scenes.length === 1 ? "" : "s"}.
      </p>
      <p class="est-line">
        {#if data.missing_poses > 0}
          completar el animatic ≈ <b>${estMissing.toFixed(3)}</b>
          <span class="muted">({data.missing_poses} pose{data.missing_poses === 1 ? "" : "s"})</span>
          {#if estRender != null} · {/if}
        {/if}
        {#if estRender != null}
          render estimado <b>${estRender.toFixed(2)}</b>
          <span class="muted">desde perfil {cheapProfile.key ?? cheapProfile.label ?? ""} (se elige en Producción)</span>
        {/if}
      </p>
    </div>
    <div class="gen-controls">
      <button class="machine cta" onclick={generate} disabled={busy || !hasFal || data.missing_poses === 0}>
        {busy ? "Generando…" : data.missing_poses > 0 ? `Completar animatic (${data.missing_poses})` : "✓ Animatic completo"}
      </button>
    </div>
  </div>

  {#if busy}<div class="progress mono"><span class="spin"></span>{progress}</div>{/if}
  {#if err}<p class="error">{err}</p>{/if}

  {#each scenes as sceneId}
    {@const shots = strip.filter((e) => e.scene === sceneId)}
    <div class="scene-block">
      <div class="scene-h">
        <b class="scene-id">{sceneId}</b>
        {#if shots[0]?.beat}<span class="muted beat">{shots[0].beat}</span>{/if}
      </div>
      <div class="strip">
        {#each shots as e, i (e.shot_id)}
          {@const t = transOf(e.transition_in)}
          {#if !(i === 0 && strip[0]?.shot_id === e.shot_id)}
            <div class="trans" title="entra por {t.title}">{t.icon}</div>
          {/if}
          <div class="shot card" class:pending={!e.ready}>
            <div class="shot-h">
              <span class="shot-id">{e.shot_id}</span>
              <span class="dur">{e.duration_s}s</span>
            </div>
            <div class="poses">
              <div class="pose">
                {#if e.start}
                  <img src={e.start} alt="apertura {e.shot_id}" loading="lazy" />
                  <button class="regen" title="No convence: descartar y regenerar esta pose"
                          disabled={busy || dropping === `${e.shot_id}/start`}
                          onclick={() => regenPose(e.shot_id, "start")}>↻</button>
                {:else}
                  <div class="hole">apertura</div>
                {/if}
                <span class="pose-lbl">apertura</span>
              </div>
              <span class="arrow">→</span>
              <div class="pose">
                {#if e.destino}
                  <img src={e.destino} alt="destino {e.shot_id}" loading="lazy" />
                  <button class="regen" title="No convence: descartar y regenerar esta pose"
                          disabled={busy || dropping === `${e.shot_id}/destino`}
                          onclick={() => regenPose(e.shot_id, "destino")}>↻</button>
                {:else}
                  <div class="hole">destino</div>
                {/if}
                <span class="pose-lbl">destino</span>
              </div>
            </div>
            {#if e.intention}<p class="intent" title="la función dramática del plano">{e.intention}</p>{/if}
          </div>
        {/each}
      </div>
    </div>
  {/each}

  <div class="savebar">
    {#if allReady}
      <span class="saved-seal">✓ Animatic completo — esto es lo que el render va a interpolar</span>
      <button class="primary cta" onclick={() => goTo("producir")}>Siguiente: Producir →</button>
    {:else}
      <span class="muted">Completá las poses para ver la película entera antes de gastar en video.</span>
      <button class="ghost" onclick={() => goTo("producir")}
              title="Podés producir igual: el render genera las poses que falten">Saltar a Producir</button>
    {/if}
  </div>
{:else if !err}
  <div class="progress mono"><span class="spin"></span>Leyendo el animatic…</div>
{:else}
  <p class="error">{err}</p>
{/if}

<style>
  .head { margin-bottom: 18px; }
  .head h1 { margin: 5px 0 8px; }
  .lede { max-width: 58ch; color: var(--ink-2); font-size: 16px; }
  .lede .r { color: var(--red-deep); }
  .generate { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; padding: 16px 20px; margin-bottom: 14px; }
  .gen-l { flex: 1; min-width: 240px; }
  .gen-help { font-size: 13px; margin: 4px 0 0; }
  .gen-controls { display: flex; align-items: center; gap: 9px; }
  .est-line { font-size: 12.5px; margin: 6px 0 0; }
  .est-line b { color: var(--ink); font-family: var(--font-mono); }
  .progress { display: flex; align-items: center; gap: 10px; background: var(--blue-wash); border: 1px solid #b9c2ee; color: var(--blue-deep); border-radius: var(--r); padding: 10px 14px; font-size: 13px; }
  .spin { width: 13px; height: 13px; border: 2px solid var(--blue-deep); border-right-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .scene-block { margin: 18px 0 10px; }
  .scene-h { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
  .scene-id { font-family: var(--font-mono); color: var(--blue-deep); font-size: 15px; }
  .beat { font-size: 12.5px; }

  /* la cinta: planos en orden con la transición de entrada entre tiles */
  .strip { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .trans {
    flex-shrink: 0; width: 30px; height: 30px; display: grid; place-items: center;
    border-radius: 50%; border: 1.5px dashed var(--line-2); color: var(--ink-soft);
    font-size: 13px; background: var(--paper-2);
  }
  .shot { padding: 10px 12px; min-width: 240px; }
  .shot.pending { border: 1.5px dashed var(--warn, #e0a93b); }
  .shot-h { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; }
  .shot-id { font-family: var(--font-mono); font-size: 12.5px; font-weight: 700; color: var(--ink-2); }
  .dur { font-family: var(--font-mono); font-size: 11px; color: var(--ink-soft); }
  .poses { display: flex; align-items: center; gap: 7px; }
  .pose { position: relative; display: flex; flex-direction: column; gap: 3px; line-height: 0; }
  .pose img { display: block; width: 96px; height: 96px; object-fit: cover; border-radius: var(--r-sm); border: 1px solid var(--line-2); }
  .pose-lbl { font-size: 9.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); line-height: 1.2; }
  .hole {
    width: 96px; height: 96px; display: grid; place-items: center; border-radius: var(--r-sm);
    border: 1.5px dashed var(--line-2); color: var(--ink-soft); font-size: 10px; line-height: 1.2;
    background: var(--paper-2);
  }
  .arrow { color: var(--ink-soft); font-size: 15px; }
  .regen {
    position: absolute; top: 4px; right: 4px; z-index: 2; width: 22px; height: 22px;
    padding: 0; line-height: 1; border-radius: 50%; border: none; cursor: pointer;
    background: rgba(0,0,0,0.55); color: #fff; font-size: 12px;
    opacity: 0; transition: opacity 0.12s ease; box-shadow: 0 1px 4px rgba(0,0,0,0.5);
  }
  .pose:hover .regen { opacity: 1; }
  .regen:hover { background: var(--red); }
  .intent { font-size: 11.5px; color: var(--ink-soft); margin: 8px 0 0; max-width: 230px; line-height: 1.4; }

  .savebar { position: sticky; bottom: 0; margin-top: 26px; padding: 16px 0 8px; background: linear-gradient(0deg, var(--paper) 60%, transparent); display: flex; align-items: center; gap: 14px; }
  .saved-seal { font-size: 13px; font-weight: 700; color: var(--ok); background: var(--ok-wash); border-radius: 999px; padding: 6px 14px; }
  .muted { color: var(--ink-soft); }
</style>
