<script>
  // [D-061] Etapa 3 · Casting: QUIÉNES son. Una página = una decisión.
  // [D-084] Patrón fluido de Encuadres: variantes con ajuste, subir, descartar.
  // [D-085] Patrón COMPLETO: el prompt del personaje visible y editable (panel
  // "Para la IA"), como la descripción visual de la escena en Encuadres. La cara
  // es un checkpoint humano (FILOSOFIA §3): merece ver y tocar lo que la IA recibe.
  import { onMount } from "svelte";
  import { get, post, put, del, humanError, bufToBase64 } from "../lib/api.js";
  import { studio, goTo, refreshStatus, GLOSARIO } from "../lib/studio.svelte.js";
  import { jobState, findLiveJob } from "../lib/jobs.svelte.js";
  import { picksFromDisk } from "../lib/picks.js";
  import BackendToggle from "../components/BackendToggle.svelte";
  import GenerateBar from "../components/GenerateBar.svelte";
  import LightTable from "../components/LightTable.svelte";
  import Progress from "../components/Progress.svelte";
  import SaveBar from "../components/SaveBar.svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import WarnBanner from "../components/WarnBanner.svelte";

  let { slug } = $props();
  let cast = $state({});          // personaje -> [urls]
  let castSources = $state({});   // personaje -> ["ia"|"upload"]
  let picks = $state({});         // personaje -> indice
  let chars = $state([]);         // personajes con design (del spec) — la fuente
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);
  let genBackend = $state("fal");
  const gen = jobState();         // generación global (todos los personajes)
  const charGen = jobState();     // generación por personaje (key = nombre)
  let uploadBusy = $state("");    // personaje subiendo imagen
  let charErr = $state({});       // personaje -> error
  let charTweak = $state({});     // personaje -> ajuste rápido de una variante

  // D-085: el panel "Para la IA" por personaje (espejo del prompt de Encuadres)
  let designEdits = $state({});   // nombre -> {prompt, physical, wardrobe, palette, expression}
  let designComposed = $state({});// nombre -> prompt compuesto (preview de lo que se envía)
  let designOpen = $state({});
  let designSaved = $state({});
  let designErr = $state({});

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);
  let anyBusy = $derived(gen.busy || charGen.busy || !!uploadBusy);

  let brokenCast = $derived(studio.status?.integrity?.casting ?? []);
  let estPerImg = $derived(studio.status?.est_cost_per_image_usd ?? 0.003);
  let castNeeded = $derived(chars.length);
  // Costo SIEMPRE visible antes del botón que gasta (D-052/D-055/D-061).
  let estCost = $derived(Math.max(castNeeded, 1) * n * estPerImg);

  let anyPick = $derived(Object.keys(picks).length > 0);
  const palStr = (p) => (p || []).join(", ");

  async function load() {
    try {
      const [c, spec] = await Promise.all([
        get(`/api/projects/${slug}/candidates`),
        get(`/api/projects/${slug}`),
      ]);
      cast = c.cast || {};
      castSources = c.cast_sources || {};
      picks = { ...picksFromDisk(c.cast_selections, cast), ...picks };
      chars = (spec.characters || []).filter((ch) => ch.design_fields);
      for (const ch of chars) {
        designComposed[ch.name] = ch.design || "";
        if (!designEdits[ch.name]) {
          const d = ch.design_fields;
          designEdits[ch.name] = {
            prompt: d.prompt || "", physical: d.physical || "",
            wardrobe: d.wardrobe || "", palette: d.palette || [],
            expression: d.expression || "",
          };
        }
      }
    } catch (e) { err = humanError(e); }
  }
  onMount(async () => {
    await load();
    // T2.6.9: F5 a mitad de la generación -> re-engancharse al job vivo.
    const live = await findLiveJob(["cast"], slug);
    if (!live) return;
    if (live.project.includes("/")) {
      charGen.attach(live.id, { key: live.project.slice(slug.length + 1), onDone: load });
    } else {
      gen.attach(live.id, { onDone: async () => { await load(); await refreshStatus(); } });
    }
  });

  function generate() {
    err = ""; saved = false;
    gen.run(`/api/projects/${slug}/cast?n=${n}&backend=${genBackend}`, {
      onDone: async () => { await load(); await refreshStatus(); },
    });
  }

  function generateChar(name) {
    charErr[name] = "";
    const tweak = (charTweak[name] || "").trim();
    charGen.run(`/api/projects/${slug}/cast/${encodeURIComponent(name)}?n=1&backend=${genBackend}`, {
      key: name,
      body: tweak ? { prompt_tweak: tweak } : {},
      onDone: async (status) => {
        if (status !== "done") charErr[name] = `Terminó como: ${status}.`;
        await load();
      },
    });
  }

  async function saveDesign(name) {
    designErr[name] = ""; designSaved[name] = false;
    const d = designEdits[name];
    try {
      const r = await put(`/api/projects/${slug}/characters/${encodeURIComponent(name)}`, {
        prompt: d.prompt, physical: d.physical, wardrobe: d.wardrobe,
        palette: d.palette, expression: d.expression,
      });
      designComposed[name] = r.design || "";
      designSaved[name] = true;
    } catch (e) { designErr[name] = humanError(e); }
  }

  async function uploadFace(name, fileInput) {
    const file = fileInput.files?.[0];
    if (!file) return;
    uploadBusy = name;
    charErr[name] = "";
    try {
      const buf = await file.arrayBuffer();
      await post(`/api/projects/${slug}/cast-candidates/${encodeURIComponent(name)}/upload`, {
        data: bufToBase64(buf), filename: file.name,
      });
      await load();
    } catch (e) {
      charErr[name] = humanError(e);
    } finally { uploadBusy = ""; fileInput.value = ""; }
  }

  async function discardFace(name, i) {
    err = "";
    try {
      await del(`/api/projects/${slug}/cast-candidates/${encodeURIComponent(name)}/${i}`);
      delete picks[name];
      await load(); await refreshStatus();
    } catch (e) { charErr[name] = humanError(e); }
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

<ViewHeader eyebrow="Paso 3 · vos decidís" title="Casting">
  <span title={GLOSARIO.casting}>La cara de cada personaje, fijada una vez.</span>
  La IA <b class="b">propone</b> varias; vos <b class="r">elegís</b> la que va.
  Esa cara viaja a todos los encuadres y planos.
</ViewHeader>

{#if chars.length === 0}
  <div class="empty card">
    <p>Este proyecto no tiene personajes con diseño de casting.</p>
    <p class="muted">Podés seguir directo a <button class="small ghost" onclick={() => goTo("encuadres")}>Encuadres →</button></p>
  </div>
{:else}
  <GenerateBar>
    {#snippet info()}
      <p class="gen-help">Genera {n} caras candidatas por personaje. La elegida se fija como identidad.</p>
      <p class="est-line">≈ <b>${estCost.toFixed(3)}</b>
        <span class="muted">por {n} caras × {castNeeded} personaje{castNeeded === 1 ? "" : "s"} con {genBackend === "google" ? "Google" : "fal"}</span></p>
    {/snippet}
    {#snippet controls()}
      <BackendToggle bind:value={genBackend} {hasGoogle} disabled={anyBusy} />
      <label class="n-lbl">opciones
        <input type="number" min="1" max="8" bind:value={n} />
      </label>
      <button class="machine cta" onclick={generate} disabled={anyBusy || !canGen}>
        {gen.busy ? "Generando…" : "Generar casting"}
      </button>
    {/snippet}
  </GenerateBar>

  {#if !canGen}
    <p class="note">🔒 Necesitás la clave de {genBackend === "google" ? "Google" : "fal.ai"}.
      <button class="small ghost" onclick={() => goTo("ajustes")}>Configurarla</button></p>
  {/if}

  {#if gen.busy}<Progress text={gen.progress || "Pidiéndole caras a la IA…"} />{/if}
  {#if err || gen.err}<p class="error">{err || gen.err}</p>{/if}

  {#if brokenCast.length}
    <WarnBanner kind="broken">
      <b>⚠ Referencias rotas.</b>
      <span>La cara de <b class="mono">{brokenCast.join(", ")}</b> ya no está en disco — regenerá el casting.</span>
    </WarnBanner>
  {/if}

  {#each chars as ch (ch.name)}
    {@const name = ch.name}
    {@const urls = cast[name] || []}
    {@const busyChar = charGen.busy && charGen.key === name}
    {@const busyUp = uploadBusy === name}
    <div class="group">
      <div class="group-h">
        <b>{name}</b>
        {#if picks[name] != null}<span class="badge red">elegido · {picks[name]}</span>{/if}
      </div>

      <!-- D-085: el prompt del personaje, visible y editable (patrón completo) -->
      {#if designEdits[name]}
        <details class="prompts-panel" bind:open={designOpen[name]}>
          <summary class="prompts-tog">Para la IA — descripción del personaje</summary>
          <div class="prompts-body">
            <span class="prompt-lbl">Cómo es {name} (entra al prompt de casting)</span>
            <textarea class="prompt-ta" rows="2" bind:value={designEdits[name].prompt}
                      oninput={() => (designSaved[name] = false)}
                      placeholder="descripción base: quién es, rasgos clave" disabled={anyBusy}></textarea>
            <div class="design-grid">
              <input bind:value={designEdits[name].physical} oninput={() => (designSaved[name] = false)}
                     placeholder="rasgos físicos" disabled={anyBusy} />
              <input bind:value={designEdits[name].wardrobe} oninput={() => (designSaved[name] = false)}
                     placeholder="vestuario" disabled={anyBusy} />
              <input value={palStr(designEdits[name].palette)}
                     oninput={(e) => { designEdits[name].palette = e.target.value.split(",").map(x => x.trim()).filter(Boolean); designSaved[name] = false; }}
                     placeholder="paleta: cyan, ámbar" disabled={anyBusy} />
              <input bind:value={designEdits[name].expression} oninput={() => (designSaved[name] = false)}
                     placeholder="expresión característica" disabled={anyBusy} />
            </div>
            {#if designComposed[name]}
              <p class="composed"><span class="composed-lbl">Prompt completo</span>{designComposed[name]}</p>
            {/if}
            <div class="prompts-foot">
              {#if designErr[name]}<span class="sm-err">{designErr[name]}</span>{/if}
              {#if designSaved[name]}<span class="saved-ok">✓ guardado · pedí variantes para verlo</span>{/if}
              <span class="foot-hint">Cambiar la descripción regenera las caras (la elegida queda hasta entonces).</span>
              <button class="small ghost" onclick={() => saveDesign(name)} disabled={anyBusy}>
                Guardar descripción
              </button>
            </div>
          </div>
        </details>
      {/if}

      <div class="char-ctrl">
        <input class="tweak-in" bind:value={charTweak[name]}
               placeholder="ajuste rápido de UNA variante: 'más serio', 'de perfil'…"
               disabled={anyBusy} />
        <button class="small machine" onclick={() => generateChar(name)}
                disabled={anyBusy || !canGen}>
          {busyChar ? "Generando…" : urls.length ? "+ variantes" : "Generar caras"}
        </button>
        <label class="small ghost upload-lbl" class:disabled={anyBusy}>
          {busyUp ? "Subiendo…" : "Subir cara"}
          <input type="file" accept="image/png,image/jpeg,image/webp" class="file-hidden"
                 disabled={anyBusy}
                 onchange={(e) => uploadFace(name, e.currentTarget)} />
        </label>
      </div>

      {#if busyChar}
        <Progress small text={charGen.progress || "Generando…"} />
      {/if}
      {#if charErr[name]}<p class="error sm-err">{charErr[name]}</p>{/if}

      {#if urls.length}
        <LightTable {urls} picked={picks[name] ?? null}
                    sources={castSources[name]}
                    disabled={anyBusy}
                    onpick={(i) => { picks[name] = i; saved = false; }}
                    ondiscard={(i) => discardFace(name, i)} />
      {:else if !busyChar}
        <p class="muted no-cands">Sin caras todavía — generá o subí una.</p>
      {/if}
    </div>
  {/each}

  <SaveBar>
    {#if saved}
      <span class="saved-seal">✓ Casting fijado</span>
      <button class="primary cta" onclick={() => goTo("encuadres")}>Siguiente: Encuadres →</button>
    {:else}
      <button class="primary cta" onclick={save} disabled={!anyPick}>Fijar casting</button>
      {#if !anyPick}<span class="muted">Hacé clic en la cara que va.</span>{/if}
    {/if}
  </SaveBar>
{/if}

<style>
  .char-ctrl { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tweak-in { flex: 1; min-width: 200px; font-size: 13px; padding: 5px 10px; background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm); }
  .upload-lbl { cursor: pointer; user-select: none; display: inline-flex; align-items: center; }
  .upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .file-hidden { display: none; }
  .sm-err { font-size: 13px; margin: 0 0 8px; }
  .no-cands { font-size: 13px; margin: 0 0 4px; }

  /* D-085: panel "Para la IA" (espejo del de Encuadres) */
  .prompts-panel { margin-bottom: 10px; border: 1px dashed var(--line-2); border-radius: var(--r-sm); background: var(--paper-2); }
  .prompts-tog { cursor: pointer; list-style: none; padding: 8px 12px; font-size: 11px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.10em; display: flex; align-items: center; gap: 6px; }
  .prompts-tog::-webkit-details-marker { display: none; }
  .prompts-tog::before { content: "▶"; font-size: 9px; transition: transform 0.15s; }
  details[open] > .prompts-tog::before { transform: rotate(90deg); }
  .prompts-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
  .prompt-lbl { font-size: 10px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.08em; }
  .prompt-ta { width: 100%; resize: vertical; font-size: 13px; line-height: 1.55; background: var(--card); border-color: var(--line); border-radius: var(--r-sm); padding: 6px 9px; font-family: var(--font-sans); color: var(--ink-2); }
  .design-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .design-grid input { font-size: 12.5px; padding: 4px 8px; background: var(--card); border-color: var(--line); border-radius: var(--r-sm); color: var(--ink-2); }
  .composed { font-size: 12px; line-height: 1.5; color: var(--ink-soft); margin: 2px 0 0; background: var(--card); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 6px 9px; }
  .composed-lbl { display: block; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-soft); margin-bottom: 3px; }
  .prompts-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .foot-hint { font-size: 11px; color: var(--ink-soft); flex: 1; }
  .saved-ok { color: var(--ok); font-size: 12px; font-weight: 600; }
</style>
