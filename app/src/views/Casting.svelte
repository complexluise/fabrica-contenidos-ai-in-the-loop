<script>
  // [D-061] Etapa 3 · Casting: QUIÉNES son. Una página = una decisión.
  // [D-081] Reescrita sobre las piezas compartidas: jobState (ciclo de job),
  // picksFromDisk (reconciliación), LightTable/GenerateBar/etc. El slug ya no
  // se vigila: App remonta la vista con {#key studio.slug}.
  import { onMount } from "svelte";
  import { get, post, humanError } from "../lib/api.js";
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
  let cast = $state({});          // personaje -> [urls]
  let picks = $state({});         // personaje -> indice
  let err = $state("");
  let saved = $state(false);
  let n = $state(2);
  let genBackend = $state("fal");
  const gen = jobState();

  let hasFal = $derived(!!studio.status?.keys?.fal_key);
  let hasGoogle = $derived(!!studio.status?.keys?.google_api_key);
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
      picks = { ...picksFromDisk(c.cast_selections, cast), ...picks };
    } catch (e) { err = humanError(e); }
  }
  onMount(load);

  function generate() {
    err = ""; saved = false;
    gen.run(`/api/projects/${slug}/cast?n=${n}&backend=${genBackend}`, {
      onDone: async () => { await load(); await refreshStatus(); },
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
      <BackendToggle bind:value={genBackend} {hasGoogle} disabled={gen.busy} />
      <label class="n-lbl">opciones
        <input type="number" min="1" max="8" bind:value={n} />
      </label>
      <button class="machine cta" onclick={generate} disabled={gen.busy || !canGen}>
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
      <div class="group">
        <div class="group-h">
          <b>{name}</b>
          {#if picks[name] != null}<span class="badge red">elegido · {picks[name]}</span>{/if}
        </div>
        <LightTable {urls} picked={picks[name] ?? null}
                    onpick={(i) => { picks[name] = i; saved = false; }} />
      </div>
    {/each}
  {:else if !gen.busy}
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
</style>
