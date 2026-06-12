<script>
  // [D-061] Etapa 4 · Encuadres: cómo se VE cada escena. La imagen clave elegida
  // acá es el DESTINO del plano ancla (D-060): donde el clip aterriza.
  import { get, post, put, del, runJob, humanError, bufToBase64 } from "../lib/api.js";
  import { studio, goTo, refreshStatus, GLOSARIO } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let cand = $state({ keyframes: {} });
  let picks = $state({});
  let busy = $state("");
  let progress = $state("");
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);
  let conc = $state(5);

  let projectSpec = $state(null);
  let promptEdits = $state({});
  let promptState = $state({});
  let promptsOpen = $state({});
  let promptsSaved = $state({});
  let promptsErr = $state({});
  let promptsBusy = $state({});
  let sceneTweak = $state({});
  let sceneErr = $state({});

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
  let genBackend = $state("fal");
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);

  let castNeeded = $derived(studio.status?.casting?.needed ?? 0);
  let castChosen = $derived(studio.status?.casting?.chosen ?? 0);
  let castReady = $derived(castNeeded === 0 || castChosen >= castNeeded);

  let brokenSel = $derived(studio.status?.integrity?.selections ?? []);
  let advisories = $derived(studio.status?.advisories ?? []);
  let sceneCount = $derived(projectSpec?.scenes?.length ?? 0);
  let estPerImg = $derived(studio.status?.est_cost_per_image_usd ?? 0.003);
  // Costo SIEMPRE visible antes del botón que gasta (D-052/D-055/D-061).
  let estCost = $derived(sceneCount * n * estPerImg);

  const entries = (o) => Object.entries(o || {});
  let hasKf = $derived(entries(cand.keyframes).length > 0);
  let anyPick = $derived(Object.keys(picks).length > 0);
  let allPicked = $derived(entries(cand.keyframes).every(([id]) => picks[id] != null));

  async function load() {
    try {
      const [c, spec] = await Promise.all([
        get(`/api/projects/${slug}/candidates`),
        get(`/api/projects/${slug}`),
      ]);
      cand = c;
      projectSpec = spec;
      if (!Object.keys(promptEdits).length) {
        const edits = {};
        for (const s of (spec.scenes || [])) {
          edits[s.id] = {
            prompt: s.prompt || "",
            framings: (s.shots || []).map(sh => sh.framing || ""),
          };
        }
        promptEdits = edits;
      }
      const states = {};
      for (const s of (spec.scenes || []))
        states[s.id] = { manual: !!s.prompt_manual, stale: !!s.prompt_stale };
      promptState = states;
      const fromDisk = {};
      for (const [sceneId, selPath] of Object.entries(cand.selections || {})) {
        const urls = cand.keyframes?.[sceneId] || [];
        const filename = String(selPath).split(/[/\\]/).pop();
        const idx = urls.findIndex((url) => url.split("/").pop() === filename);
        if (idx >= 0) fromDisk[sceneId] = idx;
      }
      picks = { ...fromDisk, ...picks };
    } catch (e) { err = humanError(e); }
  }
  $effect(() => {
    if (slug) {
      picks = {}; progress = ""; err = ""; saved = false;
      sceneTweak = {}; sceneErr = {}; promptEdits = {}; promptsOpen = {};
      promptsSaved = {}; promptsErr = {}; promptState = {}; promptsBusy = {};
      projectSpec = null;
      load();
    }
  });

  function generate() {
    busy = "keyframes"; err = ""; saved = false;
    progress = "Pidiéndole opciones a la IA…";
    runJob(`/api/projects/${slug}/keyframes?n=${n}&backend=${genBackend}&concurrency=${conc}`, {
      onLine: (l) => (progress = l),
      onDone: async (status) => {
        busy = "";
        progress = status === "done" ? "Listo. Elegí abajo." : "";
        if (status !== "done") err = `La generación terminó como: ${status}.`;
        await load(); await refreshStatus();
      },
      onError: (e) => { busy = ""; progress = ""; err = humanError(e); },
    });
  }

  function generateScene(sceneId) {
    busy = `scene:${sceneId}`;
    sceneErr = { ...sceneErr, [sceneId]: "" };
    const tweak = (sceneTweak[sceneId] || "").trim();
    runJob(`/api/projects/${slug}/keyframes/${sceneId}?n=1&backend=${genBackend}`, {
      body: tweak ? { prompt_tweak: tweak } : {},
      onLine: (l) => (progress = l),
      onDone: async (status) => {
        busy = "";
        if (status !== "done") sceneErr = { ...sceneErr, [sceneId]: `Terminó como: ${status}.` };
        await load();
      },
      onError: (e) => { busy = ""; sceneErr = { ...sceneErr, [sceneId]: humanError(e) }; },
    });
  }

  async function uploadImage(sceneId, fileInput) {
    const file = fileInput.files?.[0];
    if (!file) return;
    busy = `upload:${sceneId}`;
    sceneErr = { ...sceneErr, [sceneId]: "" };
    try {
      const buf = await file.arrayBuffer();
      await post(`/api/projects/${slug}/candidates/${sceneId}/upload`, {
        data: bufToBase64(buf), filename: file.name,
      });
      await load();
    } catch (e) {
      sceneErr = { ...sceneErr, [sceneId]: humanError(e) };
    } finally { busy = ""; fileInput.value = ""; }
  }

  async function compilePrompt(sceneId) {
    promptsErr = { ...promptsErr, [sceneId]: "" };
    promptsBusy = { ...promptsBusy, [sceneId]: true };
    try {
      const r = await post(`/api/projects/${slug}/prompts/compile`, { scene_id: sceneId });
      const c = (r.compiled || []).find(x => x.id === sceneId);
      if (c) {
        promptEdits = { ...promptEdits, [sceneId]: { ...promptEdits[sceneId], prompt: c.prompt } };
        promptState = { ...promptState, [sceneId]: { manual: c.prompt_manual, stale: c.prompt_stale } };
        promptsSaved = { ...promptsSaved, [sceneId]: true };
      }
      if (projectSpec) projectSpec = await get(`/api/projects/${slug}`);
    } catch (e) {
      promptsErr = { ...promptsErr, [sceneId]: humanError(e) };
    } finally {
      promptsBusy = { ...promptsBusy, [sceneId]: false };
    }
  }

  async function savePrompts(sceneId) {
    if (!projectSpec) return;
    promptsErr = { ...promptsErr, [sceneId]: "" };
    try {
      const body = {
        sign: false,
        title: projectSpec.title || "",
        brief: projectSpec.brief || "",
        scenes: (projectSpec.scenes || []).map(s => {
          const edits = promptEdits[s.id];
          return {
            id: s.id,
            beat: s.beat || null,
            prompt: (s.id === sceneId ? edits?.prompt : s.prompt) ?? s.prompt,
            dialogue: s.dialogue || null,
            ambience: s.ambience || null,
            shots: (s.shots || []).map((sh, j) => ({
              framing: (s.id === sceneId ? edits?.framings?.[j] : sh.framing) ?? sh.framing ?? "",
              duration_s: Number(sh.duration_s) || 1,
              voiceover: sh.voiceover || null,
              caption: sh.caption || null,
              sfx: sh.sfx || null,
            })),
          };
        }),
      };
      await put(`/api/projects/${slug}`, body);
      projectSpec = await get(`/api/projects/${slug}`);
      const fresh = (projectSpec.scenes || []).find(s => s.id === sceneId);
      if (fresh)
        promptState = { ...promptState, [sceneId]: { manual: !!fresh.prompt_manual, stale: !!fresh.prompt_stale } };
      promptsSaved = { ...promptsSaved, [sceneId]: true };
      await refreshStatus();
    } catch (e) {
      promptsErr = { ...promptsErr, [sceneId]: humanError(e) };
    }
  }

  let bulkBusy = $state("");
  let bulkMsg = $state("");
  async function compileAllPrompts(force = false) {
    bulkBusy = "prompts"; bulkMsg = ""; err = "";
    try {
      const r = await post(`/api/projects/${slug}/prompts/compile`, force ? { force: true } : {});
      const nC = (r.compiled || []).length;
      bulkMsg = nC ? `Compilados ${nC} prompt(s).` : "Todo en sintonía.";
      await load();
    } catch (e) { err = humanError(e); } finally { bulkBusy = ""; }
  }

  async function savePicks() {
    err = "";
    try {
      await post(`/api/projects/${slug}/pick`, { picks });
      saved = true;
      await load(); await refreshStatus();
    } catch (e) { err = humanError(e); }
  }

  async function discardCandidate(sceneId, i) {
    err = "";
    try {
      await del(`/api/projects/${slug}/candidates/${sceneId}/${i}`);
      const np = { ...picks }; delete np[sceneId]; picks = np;
      await load(); await refreshStatus();
    } catch (e) { err = humanError(e); }
  }
</script>

<header class="head">
  <div class="eyebrow">Paso 4 · vos decidís</div>
  <h1>Encuadres</h1>
  <p class="lede">
    <span title={GLOSARIO.keyframe}>La imagen clave de cada escena</span> — el momento donde el plano
    <b class="r">aterriza</b>. La IA <b class="b">propone</b> candidatos; vos elegís el de cada escena.
  </p>
</header>

{#if !castReady}
  <div class="warn-banner advisory">
    <b>Primero el casting.</b>
    <span>Fijá la cara de los personajes antes de encuadrar (la identidad viaja a cada imagen).
      <button class="small ghost" onclick={() => goTo("casting")}>Ir a Casting →</button></span>
  </div>
{/if}

<div class="generate card">
  <div class="gen-l">
    <div class="eyebrow" style="color:var(--blue-deep)">La IA propone</div>
    <p class="muted gen-help">Genera un puñado de candidatos para todas las escenas a la vez.</p>
    {#if sceneCount > 0}
      <p class="est-line">≈ <b>${estCost.toFixed(3)}</b>
        <span class="muted">por {n} × {sceneCount} encuadres con {genBackend === "google" ? "Google" : "fal"}</span></p>
    {/if}
  </div>
  <div class="gen-controls">
    <div class="backend-toggle" title="Motor de imagen (D-051/D-053)">
      <span class="bt-lbl">motor</span>
      <button class="bt-opt" class:active={genBackend === "fal"} disabled={!!busy}
              onclick={() => (genBackend = "fal")}>fal</button>
      <button class="bt-opt" class:active={genBackend === "google"} disabled={!!busy || !hasGoogle}
              onclick={() => (genBackend = "google")}
              title={hasGoogle ? "Gemini imagen (sin fal)" : "Falta GOOGLE_API_KEY"}>Google</button>
    </div>
    <label class="n-lbl">opciones
      <input type="number" min="1" max="8" bind:value={n} />
    </label>
    <label class="n-lbl" title="Cuántas escenas se generan en paralelo (T6/D-055)">velocidad
      <select bind:value={conc} disabled={!!busy}>
        <option value={1}>1×</option>
        <option value={3}>3×</option>
        <option value={5}>5×</option>
      </select>
    </label>
    <button class="machine cta" onclick={generate} disabled={!!busy || !canGen || !castReady}
            title={castReady ? "" : "Primero fijá el casting"}>
      {busy === "keyframes" ? "Generando…" : "Generar encuadres"}
    </button>
  </div>
</div>

{#if !canGen}
  <p class="note">🔒 Necesitás la clave de {genBackend === "google" ? "Google" : "fal.ai"}.
    <button class="small ghost" onclick={() => goTo("ajustes")}>Configurarla</button></p>
{/if}

<div class="bulk-bar">
  <span class="bulk-lbl">En lote:</span>
  <button class="small ghost" onclick={() => compileAllPrompts(false)} disabled={!!bulkBusy}>
    {bulkBusy === "prompts" ? "Compilando…" : "↻ Compilar prompts desactualizados"}
  </button>
  <button class="small ghost" onclick={() => compileAllPrompts(true)} disabled={!!bulkBusy}
          title="Recompila TODOS desde la narrativa (pisa lo manual)">Recompilar todos</button>
  {#if bulkMsg}<span class="bulk-msg">{bulkMsg}</span>{/if}
</div>

{#if busy === "keyframes"}
  <div class="progress mono"><span class="spin"></span>{progress}</div>
{/if}
{#if err}<p class="error">{err}</p>{/if}

{#if brokenSel.length}
  <div class="warn-banner broken">
    <b>⚠ Referencias rotas.</b>
    <span>El encuadre elegido de <b class="mono">{brokenSel.join(", ")}</b> ya no está en disco — regenerá y volvé a elegir.</span>
  </div>
{/if}

{#if advisories.length}
  <div class="warn-banner advisory">
    <b>Avisos del plan:</b>
    <ul>
      {#each advisories as a}
        <li><b class="mono">{a.scene}</b> {a.msg}</li>
      {/each}
    </ul>
  </div>
{/if}

{#if hasKf}
  {#each entries(cand.keyframes) as [sceneId, urls]}
    {@const busyScene = busy === `scene:${sceneId}`}
    {@const busyUpload = busy === `upload:${sceneId}`}
    {@const anyBusy = !!busy}
    <div class="group">
      <div class="group-h">
        <b class="scene-id">{sceneId}</b>
        {#if picks[sceneId] != null}<span class="badge red">elegido · {picks[sceneId]}</span>{/if}
      </div>

      {#if promptEdits[sceneId]}
        {@const pst = promptState[sceneId] || {}}
        {@const compiling = !!promptsBusy[sceneId]}
        <details class="prompts-panel" bind:open={promptsOpen[sceneId]}>
          <summary class="prompts-tog">
            Para la IA — prompt visual
            {#if pst.manual}
              <span class="pbadge manual" title="Lo editaste a mano; no se recompila solo">manual</span>
            {:else if pst.stale}
              <span class="pbadge stale" title="La narrativa cambió desde la última compilación">⚠ desactualizado</span>
            {:else}
              <span class="pbadge synced" title="En sintonía con la narrativa firmada">✓ en sintonía</span>
            {/if}
          </summary>
          <div class="prompts-body">
            <div class="prompt-lbl-row">
              <span class="prompt-lbl">Descripción visual de la escena</span>
              <button class="compile-btn" onclick={() => compilePrompt(sceneId)}
                      disabled={anyBusy || compiling}
                      title="Reescribe el prompt desde el beat, diálogo, ambience y personajes">
                {compiling ? "Compilando…" : "↻ Compilar desde la narrativa"}
              </button>
            </div>
            <textarea class="prompt-ta" rows="3" bind:value={promptEdits[sceneId].prompt}
                      placeholder="setting + personajes + acción física" disabled={anyBusy || compiling}></textarea>
            {#each (promptEdits[sceneId].framings ?? []) as _f, j}
              <div class="shot-prompt-row">
                <span class="ptag-sm">P{j + 1}</span>
                <input class="frame-in" bind:value={promptEdits[sceneId].framings[j]}
                       placeholder="encuadre del plano {j + 1}" disabled={anyBusy || compiling} />
              </div>
            {/each}
            <div class="prompts-foot">
              {#if promptsErr[sceneId]}<span class="sm-err">{promptsErr[sceneId]}</span>{/if}
              {#if promptsSaved[sceneId]}<span class="saved-ok">✓ guardado</span>{/if}
              <span class="foot-hint">Editar a mano lo marca <b>manual</b>.</span>
              <button class="small ghost" onclick={() => savePrompts(sceneId)} disabled={anyBusy || compiling}>
                Guardar prompts
              </button>
            </div>
          </div>
        </details>
      {/if}

      <div class="scene-ctrl">
        <input class="tweak-in" bind:value={sceneTweak[sceneId]}
               placeholder="ajuste opcional: 'más cerrado', 'de perfil', 'menos rojo'…"
               disabled={anyBusy} />
        <button class="small machine" onclick={() => generateScene(sceneId)}
                disabled={anyBusy || !canGen}>
          {busyScene ? "Generando…" : "+ variantes"}
        </button>
        <label class="small ghost upload-lbl" class:disabled={anyBusy}>
          {busyUpload ? "Subiendo…" : "Subir imagen"}
          <input type="file" accept="image/png,image/jpeg,image/webp" class="file-hidden"
                 disabled={anyBusy}
                 onchange={(e) => uploadImage(sceneId, e.currentTarget)} />
        </label>
      </div>

      {#if busyScene}
        <div class="scene-progress"><span class="spin sm"></span>{progress || "Generando…"}</div>
      {/if}
      {#if sceneErr[sceneId]}<p class="error sm-err">{sceneErr[sceneId]}</p>{/if}

      <div class="lighttable">
        {#each urls as url, i}
          <div class="cell-wrap">
            <button class="cell" class:sel={picks[sceneId] === i}
                    onclick={() => { picks = { ...picks, [sceneId]: i }; saved = false; }}>
              <img src={url} alt="{sceneId} {i}" loading="lazy" />
              <span class="idx">{i}</span>
              {#if cand.keyframe_sources?.[sceneId]?.[i] === "upload"}
                <span class="src-badge" title="La subiste vos; no la generó la IA">tu foto</span>
              {/if}
              {#if picks[sceneId] === i}<span class="stamp">elegido</span>{/if}
            </button>
            <button class="discard" title="Descartar este candidato"
                    onclick={() => discardCandidate(sceneId, i)} disabled={!!busy}>✕</button>
          </div>
        {/each}
      </div>
    </div>
  {/each}
{:else if !busy}
  <div class="empty card">
    <p>Todavía no hay encuadres para elegir.</p>
    <p class="muted">Usá <b>Generar encuadres</b> arriba para que la IA proponga candidatos.</p>
  </div>
{/if}

{#if hasKf}
  <div class="savebar">
    {#if saved}
      <span class="saved-seal">✓ Selección guardada</span>
      <button class="primary cta" onclick={() => goTo("animatic")}>Siguiente: Animatic →</button>
    {:else}
      <button class="primary cta" onclick={savePicks} disabled={!anyPick}>
        {allPicked ? "Confirmar selección" : "Guardar lo elegido"}
      </button>
      {#if !anyPick}<span class="muted">Hacé clic en al menos una opción.</span>{/if}
      {#if allPicked && anyPick}<span class="muted">Todas las escenas tienen encuadre. Confirmá para seguir.</span>{/if}
    {/if}
  </div>
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
  .bulk-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 9px 12px; margin-bottom: 14px; background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r-sm); }
  .bulk-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-soft); }
  .bulk-msg { font-size: 12.5px; color: var(--ok); font-weight: 600; }
  .note { background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r); padding: 9px 14px; font-size: 14px; }
  .progress { display: flex; align-items: center; gap: 10px; background: var(--blue-wash); border: 1px solid #b9c2ee; color: var(--blue-deep); border-radius: var(--r); padding: 10px 14px; font-size: 13px; }
  .spin { width: 13px; height: 13px; border: 2px solid var(--blue-deep); border-right-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
  .spin.sm { width: 11px; height: 11px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .group { margin: 14px 0 22px; }
  .group-h { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 16px; }
  .scene-id { font-family: var(--font-mono); color: var(--blue-deep); }
  .scene-ctrl { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tweak-in { flex: 1; min-width: 200px; font-size: 13px; padding: 5px 10px; background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm); }
  .upload-lbl { cursor: pointer; user-select: none; display: inline-flex; align-items: center; }
  .upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .file-hidden { display: none; }
  .scene-progress { display: flex; align-items: center; gap: 8px; color: var(--blue-deep); font-size: 12px; margin-bottom: 8px; font-family: var(--font-mono); }
  .sm-err { font-size: 13px; margin: 0 0 8px; }
  .lighttable { display: flex; flex-wrap: wrap; gap: 12px; background: #2a251e; border: 1px solid var(--line-2); border-radius: var(--r); padding: 14px; box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35); }
  .cell { position: relative; padding: 0; background: #1a1611; border: 2px solid transparent; border-radius: var(--r-sm); overflow: hidden; line-height: 0; box-shadow: none; transition: transform 0.1s ease, border-color 0.12s ease; }
  .cell:hover { transform: translateY(-3px) scale(1.01); border-color: rgba(255, 255, 255, 0.4); box-shadow: 0 8px 20px -6px rgba(0,0,0,0.6); }
  .cell img { display: block; max-width: 210px; max-height: 230px; }
  .cell.sel { border-color: var(--red); box-shadow: 0 0 0 3px var(--red-wash), 0 8px 22px -6px rgba(0,0,0,0.6); }
  .idx { position: absolute; top: 7px; left: 7px; background: rgba(0,0,0,0.62); color: #fff; border-radius: var(--r-sm); padding: 0 7px; font-family: var(--font-mono); font-size: 12px; }
  .stamp { position: absolute; top: 9px; right: -28px; transform: rotate(14deg); background: var(--red); color: #fff8f2; font-weight: 700; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 30px; box-shadow: 0 2px 6px rgba(0,0,0,0.4); }
  .cell-wrap { position: relative; line-height: 0; }
  .cell-wrap .cell { display: block; }
  .discard { position: absolute; top: 5px; right: 5px; z-index: 2; width: 22px; height: 22px; padding: 0; line-height: 1; border-radius: 50%; border: none; box-shadow: 0 1px 4px rgba(0,0,0,0.5); background: rgba(0,0,0,0.55); color: #fff; font-size: 12px; cursor: pointer; opacity: 0; transition: opacity 0.12s ease; }
  .cell-wrap:hover .discard { opacity: 1; }
  .discard:hover { background: var(--red); }
  .discard:disabled { opacity: 0; }
  .src-badge { position: absolute; bottom: 7px; left: 7px; z-index: 1; background: var(--blue-deep); color: #fff; font-size: 10px; font-weight: 700; letter-spacing: 0.04em; border-radius: var(--r-sm); padding: 1px 7px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); }
  .est-line { font-size: 12.5px; margin: 6px 0 0; }
  .est-line b { color: var(--ink); font-family: var(--font-mono); }
  .warn-banner { border-radius: var(--r); padding: 10px 14px; margin-bottom: 12px; font-size: 13.5px; display: flex; flex-direction: column; gap: 4px; }
  .warn-banner.broken { background: var(--red-wash); border: 1px solid var(--red); color: var(--red-deep); }
  .warn-banner.advisory { background: var(--warn-wash, #fbeed0); border: 1px solid var(--warn, #e0a93b); color: var(--warn-deep, #7a5400); }
  .warn-banner ul { margin: 2px 0 0; padding-left: 18px; }
  .warn-banner li { margin: 1px 0; }
  .warn-banner .mono { font-family: var(--font-mono); }
  .prompts-panel { margin-bottom: 8px; border: 1px dashed var(--line-2); border-radius: var(--r-sm); background: var(--paper-2); }
  .prompts-tog { cursor: pointer; list-style: none; padding: 8px 12px; font-size: 11px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.10em; display: flex; align-items: center; gap: 6px; }
  .prompts-tog::-webkit-details-marker { display: none; }
  .prompts-tog::before { content: "▶"; font-size: 9px; transition: transform 0.15s; }
  details[open] > .prompts-tog::before { transform: rotate(90deg); }
  .prompts-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
  .prompt-lbl-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .prompt-lbl { font-size: 10px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.08em; }
  .pbadge { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; padding: 1px 7px; border-radius: 999px; text-transform: none; }
  .pbadge.synced { background: var(--ok-wash, #e3f3e8); color: var(--ok, #2c8a4a); }
  .pbadge.stale { background: var(--warn-wash, #fbeed0); color: var(--warn-deep, #9a6b00); }
  .pbadge.manual { background: var(--blue-wash); color: var(--blue-deep); }
  .compile-btn { font-size: 11.5px; padding: 3px 10px; box-shadow: none; background: var(--blue-wash); color: var(--blue-deep); border: 1px solid var(--blue); border-radius: var(--r-sm); }
  .compile-btn:hover:not(:disabled) { background: var(--blue); color: #fff; }
  .compile-btn:disabled { opacity: 0.5; }
  .foot-hint { font-size: 11px; color: var(--ink-soft); flex: 1; }
  .prompt-ta { width: 100%; resize: vertical; font-size: 13px; line-height: 1.55; background: var(--card); border-color: var(--line); border-radius: var(--r-sm); padding: 6px 9px; font-family: var(--font-sans); color: var(--ink-2); }
  .shot-prompt-row { display: flex; align-items: center; gap: 8px; }
  .ptag-sm { background: var(--blue); color: #fff; border-radius: var(--r-sm); padding: 1px 7px; font-size: 10px; font-weight: 700; flex-shrink: 0; letter-spacing: 0.04em; }
  .frame-in { flex: 1; font-size: 12.5px; padding: 4px 8px; background: var(--card); border-color: var(--line); border-radius: var(--r-sm); color: var(--ink-2); }
  .prompts-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .saved-ok { color: var(--ok); font-size: 12px; font-weight: 600; }
  .empty { padding: 30px; text-align: center; margin-top: 16px; }
  .empty p { margin: 4px 0; }
  .savebar { position: sticky; bottom: 0; margin-top: 26px; padding: 16px 0 8px; background: linear-gradient(0deg, var(--paper) 60%, transparent); display: flex; align-items: center; gap: 14px; }
  .saved-seal { font-size: 13px; font-weight: 700; color: var(--ok); background: var(--ok-wash); border-radius: 999px; padding: 6px 14px; }
  .muted { color: var(--ink-soft); }
</style>
