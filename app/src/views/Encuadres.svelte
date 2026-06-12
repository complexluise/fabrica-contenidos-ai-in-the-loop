<script>
  // [D-061] Etapa 4 · Encuadres: cómo se VE cada escena. La imagen clave elegida
  // acá es el DESTINO del plano ancla (D-060): donde el clip aterriza.
  // [D-081] Reescrita sobre las piezas compartidas (jobState, picksFromDisk,
  // LightTable, GenerateBar...). Mutación directa de $state; App remonta la
  // vista con {#key studio.slug} — sin resets manuales.
  import { onMount } from "svelte";
  import { get, post, put, del, humanError, bufToBase64 } from "../lib/api.js";
  import { studio, goTo, refreshStatus, GLOSARIO } from "../lib/studio.svelte.js";
  import { jobState } from "../lib/jobs.svelte.js";
  import { picksFromDisk } from "../lib/picks.js";
  import BackendToggle from "../components/BackendToggle.svelte";
  import GenerateBar from "../components/GenerateBar.svelte";
  import LightTable from "../components/LightTable.svelte";
  import Progress from "../components/Progress.svelte";
  import SaveBar from "../components/SaveBar.svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import WarnBanner from "../components/WarnBanner.svelte";

  let { slug } = $props();
  let cand = $state({ keyframes: {} });
  let picks = $state({});
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);
  let conc = $state(5);
  let genBackend = $state("fal");
  const gen = jobState();        // generación global (todas las escenas)
  const sceneGen = jobState();   // generación por escena (key = scene id)
  let uploadBusy = $state("");   // scene id subiendo imagen
  let sceneErr = $state({});

  let projectSpec = $state(null);
  let promptEdits = $state({});
  let promptState = $state({});
  let promptsOpen = $state({});
  let promptsSaved = $state({});
  let promptsErr = $state({});
  let promptsBusy = $state({});
  let sceneTweak = $state({});
  let bulkBusy = $state("");
  let bulkMsg = $state("");

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);
  let anyBusy = $derived(gen.busy || sceneGen.busy || !!uploadBusy || !!bulkBusy);

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
        for (const s of (spec.scenes || [])) {
          promptEdits[s.id] = {
            prompt: s.prompt || "",
            framings: (s.shots || []).map(sh => sh.framing || ""),
          };
        }
      }
      for (const s of (spec.scenes || []))
        promptState[s.id] = { manual: !!s.prompt_manual, stale: !!s.prompt_stale };
      picks = { ...picksFromDisk(cand.selections, cand.keyframes), ...picks };
    } catch (e) { err = humanError(e); }
  }
  onMount(load);

  function generate() {
    err = ""; saved = false;
    gen.run(`/api/projects/${slug}/keyframes?n=${n}&backend=${genBackend}&concurrency=${conc}`, {
      onDone: async () => { await load(); await refreshStatus(); },
    });
  }

  function generateScene(sceneId) {
    sceneErr[sceneId] = "";
    const tweak = (sceneTweak[sceneId] || "").trim();
    sceneGen.run(`/api/projects/${slug}/keyframes/${sceneId}?n=1&backend=${genBackend}`, {
      key: sceneId,
      body: tweak ? { prompt_tweak: tweak } : {},
      onDone: async (status) => {
        if (status !== "done") sceneErr[sceneId] = `Terminó como: ${status}.`;
        await load();
      },
    });
  }

  async function uploadImage(sceneId, fileInput) {
    const file = fileInput.files?.[0];
    if (!file) return;
    uploadBusy = sceneId;
    sceneErr[sceneId] = "";
    try {
      const buf = await file.arrayBuffer();
      await post(`/api/projects/${slug}/candidates/${sceneId}/upload`, {
        data: bufToBase64(buf), filename: file.name,
      });
      await load();
    } catch (e) {
      sceneErr[sceneId] = humanError(e);
    } finally { uploadBusy = ""; fileInput.value = ""; }
  }

  async function compilePrompt(sceneId) {
    promptsErr[sceneId] = "";
    promptsBusy[sceneId] = true;
    try {
      const r = await post(`/api/projects/${slug}/prompts/compile`, { scene_id: sceneId });
      const c = (r.compiled || []).find(x => x.id === sceneId);
      if (c) {
        promptEdits[sceneId].prompt = c.prompt;
        promptState[sceneId] = { manual: c.prompt_manual, stale: c.prompt_stale };
        promptsSaved[sceneId] = true;
      }
      if (projectSpec) projectSpec = await get(`/api/projects/${slug}`);
    } catch (e) {
      promptsErr[sceneId] = humanError(e);
    } finally {
      promptsBusy[sceneId] = false;
    }
  }

  async function savePrompts(sceneId) {
    if (!projectSpec) return;
    promptsErr[sceneId] = "";
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
        promptState[sceneId] = { manual: !!fresh.prompt_manual, stale: !!fresh.prompt_stale };
      promptsSaved[sceneId] = true;
      await refreshStatus();
    } catch (e) {
      promptsErr[sceneId] = humanError(e);
    }
  }

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
      delete picks[sceneId];
      await load(); await refreshStatus();
    } catch (e) { err = humanError(e); }
  }
</script>

<ViewHeader eyebrow="Paso 4 · vos decidís" title="Encuadres">
  <span title={GLOSARIO.keyframe}>La imagen clave de cada escena</span> — el momento donde el plano
  <b class="r">aterriza</b>. La IA <b class="b">propone</b> candidatos; vos elegís el de cada escena.
</ViewHeader>

{#if !castReady}
  <WarnBanner kind="advisory">
    <b>Primero el casting.</b>
    <span>Fijá la cara de los personajes antes de encuadrar (la identidad viaja a cada imagen).
      <button class="small ghost" onclick={() => goTo("casting")}>Ir a Casting →</button></span>
  </WarnBanner>
{/if}

<GenerateBar>
  {#snippet info()}
    <p class="gen-help">Genera un puñado de candidatos para todas las escenas a la vez.</p>
    {#if sceneCount > 0}
      <p class="est-line">≈ <b>${estCost.toFixed(3)}</b>
        <span class="muted">por {n} × {sceneCount} encuadres con {genBackend === "google" ? "Google" : "fal"}</span></p>
    {/if}
  {/snippet}
  {#snippet controls()}
    <BackendToggle bind:value={genBackend} {hasGoogle} disabled={anyBusy} />
    <label class="n-lbl">opciones
      <input type="number" min="1" max="8" bind:value={n} />
    </label>
    <label class="n-lbl" title="Cuántas escenas se generan en paralelo (T6/D-055)">velocidad
      <select bind:value={conc} disabled={anyBusy}>
        <option value={1}>1×</option>
        <option value={3}>3×</option>
        <option value={5}>5×</option>
      </select>
    </label>
    <button class="machine cta" onclick={generate} disabled={anyBusy || !canGen || !castReady}
            title={castReady ? "" : "Primero fijá el casting"}>
      {gen.busy ? "Generando…" : "Generar encuadres"}
    </button>
  {/snippet}
</GenerateBar>

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

{#if gen.busy}<Progress text={gen.progress || "Pidiéndole opciones a la IA…"} />{/if}
{#if err || gen.err}<p class="error">{err || gen.err}</p>{/if}

{#if brokenSel.length}
  <WarnBanner kind="broken">
    <b>⚠ Referencias rotas.</b>
    <span>El encuadre elegido de <b class="mono">{brokenSel.join(", ")}</b> ya no está en disco — regenerá y volvé a elegir.</span>
  </WarnBanner>
{/if}

{#if advisories.length}
  <WarnBanner kind="advisory">
    <b>Avisos del plan:</b>
    <ul>
      {#each advisories as a}
        <li><b class="mono">{a.scene}</b> {a.msg}</li>
      {/each}
    </ul>
  </WarnBanner>
{/if}

{#if hasKf}
  {#each entries(cand.keyframes) as [sceneId, urls]}
    {@const busyScene = sceneGen.busy && sceneGen.key === sceneId}
    {@const busyUpload = uploadBusy === sceneId}
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
        <Progress small text={sceneGen.progress || "Generando…"} />
      {/if}
      {#if sceneErr[sceneId]}<p class="error sm-err">{sceneErr[sceneId]}</p>{/if}

      <LightTable {urls} picked={picks[sceneId] ?? null}
                  sources={cand.keyframe_sources?.[sceneId]}
                  disabled={anyBusy}
                  onpick={(i) => { picks[sceneId] = i; saved = false; }}
                  ondiscard={(i) => discardCandidate(sceneId, i)} />
    </div>
  {/each}
{:else if !anyBusy}
  <div class="empty card">
    <p>Todavía no hay encuadres para elegir.</p>
    <p class="muted">Usá <b>Generar encuadres</b> arriba para que la IA proponga candidatos.</p>
  </div>
{/if}

{#if hasKf}
  <SaveBar>
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
  </SaveBar>
{/if}

<style>
  .bulk-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 9px 12px; margin-bottom: 14px; background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r-sm); }
  .bulk-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-soft); }
  .bulk-msg { font-size: 12.5px; color: var(--ok); font-weight: 600; }
  .scene-id { font-family: var(--font-mono); color: var(--blue-deep); }
  .scene-ctrl { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tweak-in { flex: 1; min-width: 200px; font-size: 13px; padding: 5px 10px; background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm); }
  .upload-lbl { cursor: pointer; user-select: none; display: inline-flex; align-items: center; }
  .upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .file-hidden { display: none; }
  .sm-err { font-size: 13px; margin: 0 0 8px; }
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
</style>
