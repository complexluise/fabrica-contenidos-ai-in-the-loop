<script>
  // [D-061] Etapa 3 · Casting: QUIÉNES son. Una página = una decisión.
  // [D-084] Mismo patrón fluido que Encuadres: la IA propone N caras, vos
  // iterás por personaje (variantes con ajuste, subir tu propia cara, descartar)
  // y elegís. El casting es un checkpoint humano (FILOSOFIA §3): la cara viaja a
  // todo, así que merece el mismo poder de iteración que el encuadre.
  import { onMount } from "svelte";
  import { get, post, del, humanError, bufToBase64 } from "../lib/api.js";
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
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);
  let genBackend = $state("fal");
  const gen = jobState();         // generación global (todos los personajes)
  const charGen = jobState();     // generación por personaje (key = nombre)
  let uploadBusy = $state("");    // personaje subiendo imagen
  let charErr = $state({});       // personaje -> error
  let charTweak = $state({});     // personaje -> ajuste de texto

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
  let canGen = $derived(genBackend === "google" ? hasGoogle : hasFal);
  let anyBusy = $derived(gen.busy || charGen.busy || !!uploadBusy);

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
      castSources = c.cast_sources || {};
      picks = { ...picksFromDisk(c.cast_selections, cast), ...picks };
    } catch (e) { err = humanError(e); }
  }
  onMount(async () => {
    await load();
    // T2.6.9: F5 a mitad de la generación -> re-engancharse al job vivo.
    // El project del job es "slug" (global) o "slug/<personaje>" (por personaje).
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

{#if castNeeded === 0}
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
        {gen.busy ? "Generando…" : hasCast ? "Regenerar casting" : "Generar casting"}
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

  {#if hasCast}
    {#each entries(cast) as [name, urls]}
      {@const busyChar = charGen.busy && charGen.key === name}
      {@const busyUp = uploadBusy === name}
      <div class="group">
        <div class="group-h">
          <b>{name}</b>
          {#if picks[name] != null}<span class="badge red">elegido · {picks[name]}</span>{/if}
        </div>

        <div class="char-ctrl">
          <input class="tweak-in" bind:value={charTweak[name]}
                 placeholder="ajuste opcional: 'más serio', 'de perfil', 'más joven'…"
                 disabled={anyBusy} />
          <button class="small machine" onclick={() => generateChar(name)}
                  disabled={anyBusy || !canGen}>
            {busyChar ? "Generando…" : "+ variantes"}
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

        <LightTable {urls} picked={picks[name] ?? null}
                    sources={castSources[name]}
                    disabled={anyBusy}
                    onpick={(i) => { picks[name] = i; saved = false; }}
                    ondiscard={(i) => discardFace(name, i)} />
      </div>
    {/each}
  {:else if !anyBusy}
    <div class="empty card">
      <p>Todavía no hay caras para elegir.</p>
      <p class="muted">Usá <b>Generar casting</b> arriba.</p>
    </div>
  {/if}

  {#if hasCast}
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
{/if}

<style>
  .char-ctrl { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tweak-in { flex: 1; min-width: 200px; font-size: 13px; padding: 5px 10px; background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm); }
  .upload-lbl { cursor: pointer; user-select: none; display: inline-flex; align-items: center; }
  .upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .file-hidden { display: none; }
  .sm-err { font-size: 13px; margin: 0 0 8px; }
</style>
