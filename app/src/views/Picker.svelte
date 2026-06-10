<script>
  import { get, post, put, runJob, humanError, bufToBase64 } from "../lib/api.js";
  import { studio, goTo, refreshStatus } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let cand  = $state({ keyframes: {}, cast: {} });
  let kfPicks   = $state({}); // escena -> indice
  let castPicks = $state({}); // personaje -> indice
  let busy  = $state(""); // "keyframes" | "cast" | "scene:<id>" | "upload:<id>"
  let progress = $state("");
  let err   = $state("");
  let saved = $state(false);
  let n     = $state(2);

  // Prompts para la IA (cargados del spec, editables antes de generar)
  let projectSpec = $state(null);
  let promptEdits = $state({}); // { sceneId: { prompt, framings: [] } }
  let promptState = $state({}); // { sceneId: { manual, stale } } (D-046)
  let promptsOpen = $state({}); // { sceneId: bool }
  let promptsSaved = $state({}); // { sceneId: bool }
  let promptsErr  = $state({}); // { sceneId: string }
  let promptsBusy = $state({}); // { sceneId: bool } compilando

  // Estado por escena para generación individual
  let sceneTweak  = $state({}); // { sceneId: "texto del ajuste" }
  let sceneErr    = $state({}); // { sceneId: "mensaje de error" }
  let shotsBusy   = $state({}); // { sceneId: bool } generando planos encadenados (A4)

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);

  // D-051: backend de imagen del keyframe (toggle fal/Google, independiente del perfil de video).
  let genBackend = $state("fal");
  // Generar requiere la clave del backend elegido.
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);

  // Foco de generación (C3): el casting va ANTES que los encuadres.
  let castNeeded = $derived(studio.status?.casting?.needed ?? 0);
  let castChosen = $derived(studio.status?.casting?.chosen ?? 0);
  let castReady  = $derived(castNeeded === 0 || castChosen >= castNeeded);

  async function load() {
    try {
      const [c, spec] = await Promise.all([
        get(`/api/projects/${slug}/candidates`),
        get(`/api/projects/${slug}`),
      ]);
      cand = c;
      projectSpec = spec;
      // Inicializar promptEdits solo si no hay ediciones en curso
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
      // Estado del prompt (auto/manual/desactualizado) siempre fresco del backend (D-046)
      const states = {};
      for (const s of (spec.scenes || [])) {
        states[s.id] = { manual: !!s.prompt_manual, stale: !!s.prompt_stale };
      }
      promptState = states;
      // Pre-poblar kfPicks y castPicks desde las selecciones ya persistidas.
      // Tanto selections como cast_selections guardan rutas relativas;
      // buscamos el indice por nombre de archivo en el array de URLs.
      const kfFromDisk = {};
      for (const [sceneId, selPath] of Object.entries(cand.selections || {})) {
        const urls = cand.keyframes?.[sceneId] || [];
        const filename = String(selPath).split(/[/\\]/).pop();
        const idx = urls.findIndex((url) => url.split("/").pop() === filename);
        if (idx >= 0) kfFromDisk[sceneId] = idx;
      }
      const castFromDisk = {};
      for (const [name, selPath] of Object.entries(cand.cast_selections || {})) {
        const urls = cand.cast?.[name] || [];
        const filename = String(selPath).split(/[/\\]/).pop();
        const idx = urls.findIndex((url) => url.split("/").pop() === filename);
        if (idx >= 0) castFromDisk[name] = idx;
      }
      // Picks de esta sesión ganan sobre los del disco
      kfPicks   = { ...kfFromDisk,   ...kfPicks };
      castPicks = { ...castFromDisk, ...castPicks };
    } catch (e) {
      err = humanError(e);
    }
  }
  $effect(() => {
    if (slug) {
      kfPicks = {}; castPicks = {}; progress = ""; err = ""; saved = false;
      sceneTweak = {}; sceneErr = {};
      promptEdits = {}; promptsOpen = {}; promptsSaved = {}; promptsErr = {};
      promptState = {}; promptsBusy = {};
      projectSpec = null;
      load();
    }
  });

  // Generación global (todas las escenas)
  function generate(kind) {
    busy = kind; err = ""; saved = false;
    progress = "Pidiendole opciones a la IA...";
    runJob(`/api/projects/${slug}/${kind}?n=${n}&backend=${genBackend}`, {
      onLine: (l) => (progress = l),
      onDone: async (status) => {
        busy = "";
        progress = status === "done" ? "Listo. Elegi abajo." : "";
        if (status !== "done") err = `La generacion termino como: ${status}.`;
        await load(); await refreshStatus();
      },
      onError: (e) => { busy = ""; progress = ""; err = humanError(e); },
    });
  }

  // Generación por escena con prompt tweak opcional
  function generateScene(sceneId) {
    const busyKey = `scene:${sceneId}`;
    busy = busyKey;
    sceneErr = { ...sceneErr, [sceneId]: "" };
    const tweak = (sceneTweak[sceneId] || "").trim();
    const body = tweak ? { prompt_tweak: tweak } : {};
    runJob(`/api/projects/${slug}/keyframes/${sceneId}?n=1&backend=${genBackend}`,
      {
        body,
        onLine: (l) => (progress = l),
        onDone: async (status) => {
          busy = "";
          if (status !== "done")
            sceneErr = { ...sceneErr, [sceneId]: `Termino como: ${status}.` };
          await load();
        },
        onError: (e) => {
          busy = "";
          sceneErr = { ...sceneErr, [sceneId]: humanError(e) };
        },
      }
    );
  }

  // Upload de imagen propia como candidato
  async function uploadImage(sceneId, fileInput) {
    const file = fileInput.files?.[0];
    if (!file) return;
    const busyKey = `upload:${sceneId}`;
    busy = busyKey;
    sceneErr = { ...sceneErr, [sceneId]: "" };
    try {
      const buf = await file.arrayBuffer();
      await post(`/api/projects/${slug}/candidates/${sceneId}/upload`, {
        data: bufToBase64(buf), filename: file.name,
      });
      await load();
    } catch (e) {
      sceneErr = { ...sceneErr, [sceneId]: humanError(e) };
    } finally {
      busy = "";
      fileInput.value = "";
    }
  }

  // Compila el prompt de UNA escena desde la narrativa (D-046). Override explicito.
  async function compilePrompt(sceneId) {
    promptsErr = { ...promptsErr, [sceneId]: "" };
    promptsBusy = { ...promptsBusy, [sceneId]: true };
    try {
      const r = await post(`/api/projects/${slug}/prompts/compile`, { scene_id: sceneId });
      const c = (r.compiled || []).find(x => x.id === sceneId);
      if (c) {
        promptEdits = { ...promptEdits,
          [sceneId]: { ...promptEdits[sceneId], prompt: c.prompt } };
        promptState = { ...promptState,
          [sceneId]: { manual: c.prompt_manual, stale: c.prompt_stale } };
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
        promptState = { ...promptState,
          [sceneId]: { manual: !!fresh.prompt_manual, stale: !!fresh.prompt_stale } };
      promptsSaved = { ...promptsSaved, [sceneId]: true };
      await refreshStatus();
    } catch (e) {
      promptsErr = { ...promptsErr, [sceneId]: humanError(e) };
    }
  }

  // A4: genera (encadenados) los keyframes de los planos 2+ desde el ancla elegida.
  function genShotPreviews(sceneId, force = false) {
    shotsBusy = { ...shotsBusy, [sceneId]: true };
    err = "";
    runJob(`/api/projects/${slug}/shots/${sceneId}`, {
      body: { backend: genBackend, ...(force ? { force: true } : {}) },
      onDone: async (status) => {
        shotsBusy = { ...shotsBusy, [sceneId]: false };
        if (status !== "done") err = `Planos: terminó como ${status}.`;
        await load();
      },
      onError: (e) => { shotsBusy = { ...shotsBusy, [sceneId]: false }; err = humanError(e); },
    });
  }

  // --- Acciones MASIVAS (sobre todas las escenas) ---
  let bulkBusy = $state("");   // "prompts" | "shots" | ""
  let bulkMsg  = $state("");

  // Compila TODOS los prompts desactualizados de una (D-046). force=true recompila todo.
  async function compileAllPrompts(force = false) {
    bulkBusy = "prompts"; bulkMsg = ""; err = "";
    try {
      const r = await post(`/api/projects/${slug}/prompts/compile`, force ? { force: true } : {});
      const nC = (r.compiled || []).length;
      bulkMsg = nC ? `Compilados ${nC} prompt(s).` : "Todo en sintonía.";
      await load();
    } catch (e) {
      err = humanError(e);
    } finally {
      bulkBusy = "";
    }
  }

  // Genera los planos encadenados de TODAS las escenas con ancla elegida (A4).
  async function genAllShots() {
    const ids = entries(cand.keyframes).map(([id]) => id).filter(id => cand.selections?.[id]);
    if (!ids.length) { err = "Primero elegí y guardá el encuadre ancla de las escenas."; return; }
    bulkBusy = "shots"; bulkMsg = ""; err = "";
    for (const id of ids) {
      bulkMsg = `Generando planos de ${id}…`;
      try {
        await new Promise((res, rej) => {
          shotsBusy = { ...shotsBusy, [id]: true };
          runJob(`/api/projects/${slug}/shots/${id}`, {
            body: { backend: genBackend },
            onDone: (s) => { shotsBusy = { ...shotsBusy, [id]: false }; s === "done" ? res() : rej(new Error(`${id}: ${s}`)); },
            onError: (e) => { shotsBusy = { ...shotsBusy, [id]: false }; rej(e); },
          });
        });
      } catch (e) { err = humanError(e); break; }
    }
    bulkBusy = ""; bulkMsg = err ? "" : "Planos generados."; await load();
  }

  async function savePicks() {
    err = "";
    try {
      if (Object.keys(kfPicks).length)
        await post(`/api/projects/${slug}/pick`, { picks: kfPicks });
      if (Object.keys(castPicks).length)
        await post(`/api/projects/${slug}/pick-cast`, { picks: castPicks });
      saved = true;
      await refreshStatus();
    } catch (e) {
      err = humanError(e);
    }
  }

  const entries = (o) => Object.entries(o || {});
  let needsCast = $derived((studio.status?.casting?.needed ?? 0) > 0);
  let hasCast = $derived(entries(cand.cast).length > 0);
  let hasKf   = $derived(entries(cand.keyframes).length > 0);
  let nothing = $derived(!hasCast && !hasKf);
  let anyPick    = $derived(Object.keys(kfPicks).length + Object.keys(castPicks).length > 0);
  let allPicked  = $derived(
    entries(cand.keyframes).every(([id]) => kfPicks[id] != null)
  );
</script>

<header class="head">
  <div class="eyebrow">Paso 3 · vos decidís</div>
  <h1>Elegir</h1>
  <p class="lede">
    La IA <b class="b">propone</b> varias opciones para cada escena. Tu trabajo es
    el más importante: <b class="r">elegir</b> la que va. Hacé clic en la que más te guste.
  </p>
</header>

<div class="generate card">
  <div class="gen-l">
    <div class="eyebrow" style="color:var(--blue-deep)">La IA propone</div>
    <p class="muted gen-help">
      Generá un puñado de candidatos para todas las escenas a la vez.
      {#if needsCast}<b>Casting</b> = la cara del personaje (se fija una vez). {/if}
      <b>Encuadres</b> = la imagen base de cada escena.
    </p>
  </div>
  <div class="gen-controls">
    <div class="backend-toggle" title="Motor de imagen para los keyframes (D-051)">
      <span class="bt-lbl">motor</span>
      <button class="bt-opt" class:active={genBackend === "fal"} disabled={!!busy}
              onclick={() => (genBackend = "fal")}>fal</button>
      <button class="bt-opt" class:active={genBackend === "google"} disabled={!!busy || !hasGoogle}
              onclick={() => (genBackend = "google")}
              title={hasGoogle ? "Gemini 2.5 Flash Image (sin fal)" : "Falta GOOGLE_API_KEY"}>Google</button>
    </div>
    <label class="n-lbl">opciones
      <input type="number" min="1" max="8" bind:value={n} />
    </label>
    {#if needsCast && !castReady}
      <!-- Foco: primero el casting; encuadres bloqueado hasta fijar la cara -->
      <button class="machine cta" onclick={() => generate("cast")} disabled={!!busy || !canGen}>
        {busy === "cast" ? "Generando…" : "1 · Generar casting"}
      </button>
      <button class="machine" disabled title="Primero fijá la cara del personaje (casting)">
        2 · Generar encuadres
      </button>
    {:else}
      {#if needsCast}
        <button class="ghost small" onclick={() => generate("cast")} disabled={!!busy || !canGen}>
          {busy === "cast" ? "Generando…" : "Regenerar casting"}
        </button>
      {/if}
      <button class="machine cta" onclick={() => generate("keyframes")} disabled={!!busy || !canGen}>
        {busy === "keyframes" ? "Generando…" : "Generar encuadres"}
      </button>
    {/if}
  </div>
</div>

{#if !canGen}
  <p class="note">🔒 Para generar con <b>{genBackend === "google" ? "Google" : "fal"}</b> necesitás tu clave de
    {genBackend === "google" ? "Google (GOOGLE_API_KEY)" : "fal.ai"}.
    <button class="small ghost" onclick={() => goTo("ajustes")}>Configurarla</button></p>
{/if}

<!-- Acciones masivas (D-046/D-048): sobre todas las escenas de una -->
<div class="bulk-bar">
  <span class="bulk-lbl">En lote:</span>
  <button class="small ghost" onclick={() => compileAllPrompts(false)}
          disabled={!!bulkBusy}>
    {bulkBusy === "prompts" ? "Compilando…" : "↻ Compilar prompts desactualizados"}
  </button>
  <button class="small ghost" onclick={() => compileAllPrompts(true)} disabled={!!bulkBusy}
          title="Recompila TODOS desde la narrativa (pisa lo manual)">Recompilar todos</button>
  <button class="small ghost" onclick={genAllShots} disabled={!!bulkBusy || !canGen}
          title="Genera los planos encadenados de todas las escenas con ancla elegida">
    {bulkBusy === "shots" ? "Generando…" : "Generar todos los planos"}
  </button>
  {#if bulkMsg}<span class="bulk-msg">{bulkMsg}</span>{/if}
</div>

{#if busy === "keyframes" || busy === "cast"}
  <div class="progress mono"><span class="spin"></span>{progress}</div>
{/if}
{#if err}<p class="error">{err}</p>{/if}

{#if hasCast}
  <section>
    <h2 class="sec">Casting <span class="muted small-h">la cara del personaje</span></h2>
    {#each entries(cand.cast) as [name, urls]}
      <div class="group">
        <div class="group-h">
          <b>{name}</b>
          {#if castPicks[name] != null}<span class="badge red">elegido · {castPicks[name]}</span>{/if}
        </div>
        <div class="lighttable">
          {#each urls as url, i}
            <button class="cell" class:sel={castPicks[name] === i}
                    onclick={() => { castPicks = { ...castPicks, [name]: i }; saved = false; }}>
              <img src={url} alt="{name} {i}" loading="lazy" />
              <span class="idx">{i}</span>
              {#if castPicks[name] === i}<span class="stamp">elegido</span>{/if}
            </button>
          {/each}
        </div>
      </div>
    {/each}
  </section>
{/if}

{#if hasKf}
  <section>
    <h2 class="sec">Encuadres <span class="muted small-h">la imagen base de cada escena</span></h2>
    {#each entries(cand.keyframes) as [sceneId, urls]}
      {@const busyScene = busy === `scene:${sceneId}`}
      {@const busyUpload = busy === `upload:${sceneId}`}
      {@const anyBusy = !!busy}
      <div class="group">
        <div class="group-h">
          <b class="scene-id">{sceneId}</b>
          {#if kfPicks[sceneId] != null}<span class="badge red">elegido · {kfPicks[sceneId]}</span>{/if}
        </div>

        <!-- Prompts para la IA (colapsable, editable antes de generar) -->
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
                <span class="prompt-lbl">Descripcion visual de la escena</span>
                <button class="compile-btn" onclick={() => compilePrompt(sceneId)}
                        disabled={anyBusy || compiling}
                        title="Reescribe el prompt desde el beat, diálogo, ambience y personajes">
                  {compiling ? "Compilando…" : "↻ Compilar desde la narrativa"}
                </button>
              </div>
              <textarea class="prompt-ta" rows="3" bind:value={promptEdits[sceneId].prompt}
                        placeholder="setting + personajes + accion fisica" disabled={anyBusy || compiling}></textarea>
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

        <!-- Controles por escena -->
        <div class="scene-ctrl">
          <input class="tweak-in" bind:value={sceneTweak[sceneId]}
                 placeholder="ajuste opcional: 'más cerrado', 'de perfil', 'menos rojo'…"
                 disabled={anyBusy} />
          <button class="small machine" onclick={() => generateScene(sceneId)}
                  disabled={anyBusy || !hasFal}>
            {busyScene ? "Generando…" : "+ variantes"}
          </button>
          <!-- Upload: label actúa como botón, input hidden -->
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
            <button class="cell" class:sel={kfPicks[sceneId] === i}
                    onclick={() => { kfPicks = { ...kfPicks, [sceneId]: i }; saved = false; }}>
              <img src={url} alt="{sceneId} {i}" loading="lazy" />
              <span class="idx">{i}</span>
              {#if kfPicks[sceneId] === i}<span class="stamp">elegido</span>{/if}
            </button>
          {/each}
        </div>

        <!-- A4: planos encadenados desde el ancla elegida (coherencia) -->
        {#if cand.selections?.[sceneId]}
          {@const previews = cand.shot_previews?.[sceneId] || []}
          {@const shotBusy = !!shotsBusy[sceneId]}
          <div class="shots-preview">
            <div class="sp-head">
              <span class="sp-lbl">Planos de la escena <span class="muted small-h">encadenados desde tu elección</span></span>
              <button class="small ghost" onclick={() => genShotPreviews(sceneId, previews.length > 1)}
                      disabled={anyBusy || shotBusy || !hasFal}>
                {shotBusy ? "Generando…" : previews.length > 1 ? "↻ Regenerar planos" : "Generar planos"}
              </button>
            </div>
            {#if shotBusy}
              <div class="scene-progress"><span class="spin sm"></span>encadenando planos…</div>
            {:else if previews.length > 1}
              <div class="sp-strip">
                {#each previews as url, k}
                  <div class="sp-cell" class:anchor={k === 0}>
                    <img src={url} alt="plano {k + 1}" loading="lazy" />
                    <span class="sp-n">P{k + 1}{k === 0 ? " · ancla" : ""}</span>
                  </div>
                {/each}
              </div>
            {:else}
              <p class="muted sp-hint">Generá los planos para ver cómo encadenan desde el encuadre que elegiste.</p>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  </section>
{/if}

{#if nothing && !busy}
  <div class="empty card">
    <p>Todavía no hay opciones para elegir.</p>
    <p class="muted">Usá <b>Generar</b> arriba para que la IA proponga candidatos.</p>
  </div>
{/if}

{#if (hasCast || hasKf)}
  <div class="savebar">
    {#if saved}
      <span class="saved-seal">✓ Selección guardada</span>
      <button class="primary cta go" onclick={() => goTo("producir")}>Siguiente: Producir →</button>
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

  /* Toggle de backend de imagen (D-051) */
  .backend-toggle { display: inline-flex; align-items: center; gap: 0; border: 1.5px solid var(--line-2); border-radius: 999px; overflow: hidden; }
  .bt-lbl { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); padding: 0 8px 0 11px; }
  .bt-opt { border: none; border-radius: 0; box-shadow: none; background: var(--paper); padding: 6px 12px; font-size: 13px; font-weight: 600; color: var(--ink-soft); }
  .bt-opt.active { background: var(--blue); color: #fff; }
  .bt-opt:disabled { opacity: 0.4; }

  /* Barra de acciones masivas (D-046/D-048) */
  .bulk-bar {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 9px 12px; margin-bottom: 14px;
    background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r-sm);
  }
  .bulk-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-soft); }
  .bulk-msg { font-size: 12.5px; color: var(--ok); font-weight: 600; }

  .note { background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r); padding: 9px 14px; font-size: 14px; }
  .progress { display: flex; align-items: center; gap: 10px; background: var(--blue-wash); border: 1px solid #b9c2ee; color: var(--blue-deep); border-radius: var(--r); padding: 10px 14px; font-size: 13px; }
  .spin { width: 13px; height: 13px; border: 2px solid var(--blue-deep); border-right-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
  .spin.sm { width: 11px; height: 11px; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .sec { margin: 28px 0 6px; }
  .small-h { font-family: var(--font-sans); font-size: 13px; font-weight: 400; }
  .group { margin: 14px 0 22px; }
  .group-h { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 16px; }
  .scene-id { font-family: var(--font-mono); color: var(--blue-deep); }

  /* Controles por escena: tweak + generar + subir */
  .scene-ctrl {
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
  }
  .tweak-in {
    flex: 1; min-width: 200px; font-size: 13px; padding: 5px 10px;
    background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm);
  }
  .upload-lbl {
    cursor: pointer; user-select: none;
    display: inline-flex; align-items: center;
  }
  .upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .file-hidden { display: none; }
  .scene-progress {
    display: flex; align-items: center; gap: 8px;
    color: var(--blue-deep); font-size: 12px; margin-bottom: 8px;
    font-family: var(--font-mono);
  }
  .sm-err { font-size: 13px; margin: 0 0 8px; }

  /* mesa de luz */
  .lighttable {
    display: flex; flex-wrap: wrap; gap: 12px;
    background: #2a251e; border: 1px solid var(--line-2);
    border-radius: var(--r); padding: 14px;
    box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35);
  }
  .cell {
    position: relative; padding: 0; background: #1a1611; border: 2px solid transparent;
    border-radius: var(--r-sm); overflow: hidden; line-height: 0; box-shadow: none;
    transition: transform 0.1s ease, border-color 0.12s ease;
  }
  .cell:hover { transform: translateY(-3px) scale(1.01); border-color: rgba(255, 255, 255, 0.4); box-shadow: 0 8px 20px -6px rgba(0,0,0,0.6); }
  .cell img { display: block; max-width: 210px; max-height: 230px; }
  .cell.sel { border-color: var(--red); box-shadow: 0 0 0 3px var(--red-wash), 0 8px 22px -6px rgba(0,0,0,0.6); }
  .idx {
    position: absolute; top: 7px; left: 7px; background: rgba(0,0,0,0.62); color: #fff;
    border-radius: var(--r-sm); padding: 0 7px; font-family: var(--font-mono); font-size: 12px;
  }
  .stamp {
    position: absolute; top: 9px; right: -28px; transform: rotate(14deg);
    background: var(--red); color: #fff8f2; font-weight: 700; font-size: 11px;
    letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 30px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  }

  /* Panel "Para la IA" (prompts colapsables por escena) */
  .prompts-panel {
    margin-bottom: 8px; border: 1px dashed var(--line-2);
    border-radius: var(--r-sm); background: var(--paper-2);
  }
  .prompts-tog {
    cursor: pointer; list-style: none; padding: 8px 12px;
    font-size: 11px; font-weight: 700; color: var(--ink-soft);
    text-transform: uppercase; letter-spacing: 0.10em;
    display: flex; align-items: center; gap: 6px;
  }
  .prompts-tog::-webkit-details-marker { display: none; }
  .prompts-tog::before { content: "▶"; font-size: 9px; transition: transform 0.15s; }
  details[open] > .prompts-tog::before { transform: rotate(90deg); }
  .prompts-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
  .prompt-lbl-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .prompt-lbl { font-size: 10px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.08em; }

  /* Badge de estado del prompt (D-046) */
  .pbadge {
    font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
    padding: 1px 7px; border-radius: 999px; text-transform: none;
  }
  .pbadge.synced { background: var(--ok-wash, #e3f3e8); color: var(--ok, #2c8a4a); }
  .pbadge.stale  { background: var(--warn-wash, #fbeed0); color: var(--warn-deep, #9a6b00); }
  .pbadge.manual { background: var(--blue-wash); color: var(--blue-deep); }
  /* Boton compilar desde la narrativa */
  .compile-btn {
    font-size: 11.5px; padding: 3px 10px; box-shadow: none;
    background: var(--blue-wash); color: var(--blue-deep);
    border: 1px solid var(--blue); border-radius: var(--r-sm);
  }
  .compile-btn:hover:not(:disabled) { background: var(--blue); color: #fff; }
  .compile-btn:disabled { opacity: 0.5; }
  .foot-hint { font-size: 11px; color: var(--ink-soft); flex: 1; }
  .prompt-ta {
    width: 100%; resize: vertical; font-size: 13px; line-height: 1.55;
    background: var(--card); border-color: var(--line); border-radius: var(--r-sm);
    padding: 6px 9px; font-family: var(--font-sans); color: var(--ink-2);
  }
  .shot-prompt-row { display: flex; align-items: center; gap: 8px; }
  .ptag-sm {
    background: var(--blue); color: #fff; border-radius: var(--r-sm);
    padding: 1px 7px; font-size: 10px; font-weight: 700; flex-shrink: 0; letter-spacing: 0.04em;
  }
  .frame-in {
    flex: 1; font-size: 12.5px; padding: 4px 8px;
    background: var(--card); border-color: var(--line); border-radius: var(--r-sm);
    color: var(--ink-2);
  }
  .prompts-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .saved-ok { color: var(--ok); font-size: 12px; font-weight: 600; }

  .empty { padding: 30px; text-align: center; margin-top: 16px; }
  .empty p { margin: 4px 0; }

  .savebar {
    position: sticky; bottom: 0; margin-top: 26px; padding: 16px 0 8px;
    background: linear-gradient(0deg, var(--paper) 60%, transparent);
    display: flex; align-items: center; gap: 14px;
  }
  .saved-seal {
    font-size: 13px; font-weight: 700; color: var(--ok);
    background: var(--ok-wash); border-radius: 999px; padding: 6px 14px;
  }
  .muted { color: var(--ink-soft); }

  /* A4: tira de planos encadenados */
  .shots-preview {
    margin-top: 12px; padding: 12px 14px;
    background: var(--paper-2); border: 1px solid var(--line); border-radius: var(--r-sm);
  }
  .sp-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 9px; flex-wrap: wrap; }
  .sp-lbl { font-size: 12px; font-weight: 700; color: var(--ink-2); }
  .sp-hint { font-size: 12.5px; margin: 0; }
  .sp-strip { display: flex; flex-wrap: wrap; gap: 10px; }
  .sp-cell { position: relative; line-height: 0; border-radius: var(--r-sm); overflow: hidden; border: 1px solid var(--line-2); }
  .sp-cell.anchor { border-color: var(--red); box-shadow: 0 0 0 2px var(--red-wash); }
  .sp-cell img { display: block; width: 132px; height: 132px; object-fit: cover; }
  .sp-n {
    position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.6); color: #fff;
    font-family: var(--font-mono); font-size: 10.5px; padding: 2px 6px; text-align: left;
  }
</style>
