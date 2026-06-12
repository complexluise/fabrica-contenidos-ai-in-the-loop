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

  // D-063: best-of-N por pose — generar variantes y ELEGIR (no solo regenerar).
  let variantsBusy = $state("");  // "shot/which" generando variantes
  function genVariants(shotId, which) {
    variantsBusy = `${shotId}/${which}`; err = "";
    runJob(`/api/projects/${slug}/animatic/${shotId}/${which}/variants?n=3`, {
      onDone: async (status) => {
        variantsBusy = "";
        if (status !== "done") err = `Variantes: terminó como ${status}.`;
        await load();
      },
      onError: (e) => { variantsBusy = ""; err = humanError(e); },
    });
  }
  async function pickVariant(shotId, which, url) {
    err = "";
    try {
      await post(`/api/projects/${slug}/animatic/${shotId}/${which}/pick`, { path: url });
      await load(); await refreshStatus();
    } catch (e) { err = humanError(e); }
  }

  // D-062: ▶ reproducir el animatic — las poses en secuencia con sus duraciones.
  let playing = $state(false);
  let playIdx = $state(0);
  let playPose = $state("start"); // "start" | "destino" dentro del plano
  let playTimer = null;
  function stopPlay() { playing = false; if (playTimer) clearTimeout(playTimer); playTimer = null; }
  function play() {
    if (!strip.length) return;
    playing = true; playIdx = 0; playPose = "start";
    stepPlay();
  }
  function stepPlay() {
    const e = strip[playIdx];
    if (!e) { stopPlay(); return; }
    const dur = Math.max(1, e.duration_s || 2) * 1000;
    if (playPose === "start") {
      // apertura ~40% del plano, destino el resto (el clip ATERRIZA en el destino)
      playTimer = setTimeout(() => { playPose = "destino"; stepPlay(); }, dur * 0.4);
    } else {
      playTimer = setTimeout(() => {
        if (playIdx + 1 < strip.length) { playIdx += 1; playPose = "start"; stepPlay(); }
        else stopPlay();
      }, dur * 0.6);
    }
  }
  let playerShot = $derived(strip[playIdx] ?? null);
  let playerImg = $derived(playerShot ? (playPose === "start" ? playerShot.start : playerShot.destino) : null);
</script>

<header class="head">
  <div class="eyebrow">Paso 5 · vos decidís</div>
  <h1>Animatic</h1>
  <p class="lede">
    <span title={GLOSARIO.animatic}>La película completa en poses</span>, <b class="r">antes</b> de pagar
    el video. Por defecto <b>la cámara actúa</b> desde el destino elegido (un solo still);
    los planos <span class="lands-chip">aterriza</span> interpolan apertura → destino (D-070).
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
      {#if data.billing}
        <p class="est-line billing" title="El proveedor de video factura bloques de ~5s: un plano de 2s paga 5s (D-062)">
          ⏱ el corte usa <b>{data.billing.used_s.toFixed(0)}s</b> pero paga
          <b>{data.billing.paid_s.toFixed(0)}s</b> de video
          {#if data.billing.wasted_s > 0}
            <span class="waste">(~{data.billing.wasted_s.toFixed(0)}s pagados que se tiran — planos de 4-5s aprovechan el bloque)</span>
          {/if}
        </p>
      {/if}
    </div>
    <div class="gen-controls">
      <button class="ghost" onclick={play} disabled={playing || !strip.length}
              title="Las poses en secuencia con sus duraciones: el ritmo de la película, gratis">
        ▶ Reproducir
      </button>
      <button class="machine cta" onclick={generate} disabled={busy || !hasFal || data.missing_poses === 0}>
        {busy ? "Generando…" : data.missing_poses > 0 ? `Completar animatic (${data.missing_poses})` : "✓ Animatic completo"}
      </button>
    </div>
  </div>

  {#if playing && playerShot}
    <div class="player" onclick={stopPlay} role="button" tabindex="0">
      {#if playerImg}
        <img src={playerImg} alt={playerShot.shot_id} />
      {:else}
        <div class="player-hole">pose faltante</div>
      {/if}
      <div class="player-bar">
        <span class="mono">{playerShot.shot_id} · {playPose} · {playerShot.duration_s}s</span>
        <span class="muted">plano {playIdx + 1}/{strip.length} — clic para parar</span>
      </div>
    </div>
  {/if}

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
              {#if e.lands}<span class="lands-chip" title="Interpola apertura → destino (provider end-frame, 3x)">aterriza</span>{/if}
              {#if e.media === "still"}<span class="still-chip" title="Still con Ken Burns: $0 de video (D-074)">still</span>{/if}
              <span class="dur">{e.duration_s}s</span>
            </div>
            <div class="poses">
              {#each (e.lands ? ["start", "destino"] : ["destino"]) as which, wi}
                {#if e.lands && wi === 1}<span class="arrow">→</span>{/if}
                {@const img = which === "start" ? e.start : e.destino}
                {@const variants = e[`${which}_variants`] || []}
                {@const vBusy = variantsBusy === `${e.shot_id}/${which}`}
                <div class="pose">
                  {#if img}
                    <img src={img} alt="{which} {e.shot_id}" loading="lazy" />
                    {#if e[`${which}_picked`]}<span class="pick-badge" title="Variante elegida por vos">★</span>{/if}
                    <button class="regen" title="No convence: descartar y regenerar esta pose"
                            disabled={busy || dropping === `${e.shot_id}/${which}`}
                            onclick={() => regenPose(e.shot_id, which)}>↻</button>
                    <button class="vary" title="Generar 3 variantes y ELEGIR (D-063)"
                            disabled={busy || vBusy || !hasFal}
                            onclick={() => genVariants(e.shot_id, which)}>{vBusy ? "…" : "⊞"}</button>
                  {:else}
                    <div class="hole">{which === "start" ? "apertura" : "destino"}</div>
                  {/if}
                  <span class="pose-lbl">{which === "start" ? "apertura" : "destino"}</span>
                  {#if variants.length}
                    <div class="variants">
                      {#each variants as v}
                        <button class="vthumb" title="Elegir esta variante"
                                onclick={() => pickVariant(e.shot_id, which, v)}>
                          <img src={v} alt="variante" loading="lazy" />
                        </button>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/each}
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
  .dur { font-family: var(--font-mono); font-size: 11px; color: var(--ink-soft); margin-left: auto; }
  .lands-chip, .still-chip {
    font-size: 9px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 1px 7px; border-radius: 999px; line-height: 1.6;
  }
  .lands-chip { background: var(--red-wash); color: var(--red-deep); border: 1px solid var(--red); }
  .still-chip { background: var(--paper-2); color: var(--ink-soft); border: 1px solid var(--line-2); }
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

  /* D-062: la plata visible */
  .billing { color: var(--ink-2); }
  .billing .waste { color: var(--warn-deep, #9a6b00); font-size: 11.5px; }

  /* D-062: ▶ reproductor del animatic (poses en secuencia) */
  .player {
    position: fixed; inset: 0; z-index: 50; background: rgba(15, 12, 9, 0.92);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 14px; cursor: pointer;
  }
  .player img { max-height: 78vh; max-width: 92vw; border-radius: var(--r); box-shadow: 0 12px 60px rgba(0,0,0,0.6); }
  .player-hole { color: #999; font-size: 14px; }
  .player-bar { display: flex; gap: 16px; color: #ddd; font-size: 13px; }
  .player-bar .mono { font-family: var(--font-mono); }

  /* D-063: variantes por pose (best-of-N) */
  .vary {
    position: absolute; top: 4px; left: 4px; z-index: 2; width: 22px; height: 22px;
    padding: 0; line-height: 1; border-radius: 50%; border: none; cursor: pointer;
    background: rgba(0,0,0,0.55); color: #fff; font-size: 12px;
    opacity: 0; transition: opacity 0.12s ease; box-shadow: 0 1px 4px rgba(0,0,0,0.5);
  }
  .pose:hover .vary { opacity: 1; }
  .vary:hover { background: var(--blue); }
  .pick-badge {
    position: absolute; bottom: 22px; right: 4px; z-index: 2; width: 18px; height: 18px;
    display: grid; place-items: center; border-radius: 50%;
    background: var(--red); color: #fff; font-size: 11px; box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }
  .variants { display: flex; gap: 4px; margin-top: 4px; }
  .vthumb { padding: 0; border: 2px solid transparent; border-radius: var(--r-sm); overflow: hidden; line-height: 0; box-shadow: none; cursor: pointer; }
  .vthumb:hover { border-color: var(--red); }
  .vthumb img { display: block; width: 29px; height: 29px; object-fit: cover; }
</style>
