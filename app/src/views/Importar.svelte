<script>
  import { onMount } from "svelte";
  import { get, humanError } from "../lib/api.js";
  import { studio, goTo, loadProjects, setSlug } from "../lib/studio.svelte.js";
  import { jobState } from "../lib/jobs.svelte.js";
  import JobLog from "../components/JobLog.svelte";
  import ViewHeader from "../components/ViewHeader.svelte";
  import WarnStrip from "../components/WarnStrip.svelte";

  let text = $state("");
  let slug = $state("");
  let style = $state("lego");
  let styles = $state(["lego"]);
  let fileName = $state("");
  let dragging = $state(false);
  let err = $state("");
  const imp = jobState();  // D-081: el ciclo de job, una sola implementacion

  const noKey = $derived(studio.status && !studio.status.keys?.anthropic_api_key);

  onMount(async () => {
    try {
      const s = await get("/api/styles");
      if (s?.length) { styles = s; if (!s.includes(style)) style = s[0]; }
    } catch { /* deja el default */ }
  });

  async function readFile(file) {
    if (!file) return;
    if (!/\.(md|txt|markdown|text)$/i.test(file.name)) {
      err = "Sólo .md o .txt. Para otros formatos, pegá el texto.";
      return;
    }
    err = "";
    fileName = file.name;
    text = await file.text();
  }

  function onDrop(e) {
    e.preventDefault();
    dragging = false;
    readFile(e.dataTransfer?.files?.[0]);
  }

  function importar() {
    err = "";
    if (!text.trim()) {
      err = "Pegá o subí un texto primero.";
      return;
    }
    imp.run("/api/projects/import", {
      body: { text, slug: slug.trim() || undefined, style },
      onDone: async (status, jobId) => {
        if (status !== "done") return;  // imp.err ya lo cuenta
        const detail = await get(`/api/jobs/${jobId}`);
        const newSlug = detail.result?.slug;
        await loadProjects();
        if (newSlug) {
          await setSlug(newSlug);
          goTo("storyboard"); // a editar el borrador propuesto
        }
      },
    });
  }
</script>

<ViewHeader eyebrow="Paso 1 · la IA propone" title="Importar un guion">
  Pegá o subí tu texto. La IA lo descompone en un <b>borrador</b> de proyecto
    (título, sinopsis y escenas); después lo editás y firmás en el Storyboard.
</ViewHeader>

{#if noKey}
  <WarnStrip actionLabel="Ir a Ajustes →" onaction={() => goTo("ajustes")}>
    <b>Falta la clave de Anthropic.</b> La descomposición usa Claude.
  </WarnStrip>
{/if}

<div
  class="drop"
  class:dragging
  role="button"
  tabindex="0"
  ondragover={(e) => { e.preventDefault(); dragging = true; }}
  ondragleave={() => (dragging = false)}
  ondrop={onDrop}
>
  <textarea
    bind:value={text}
    placeholder="Pegá acá tu guion, brief o idea… (o arrastrá un .md / .txt)"
    rows="12"
  ></textarea>
  <div class="drop-foot">
    <label class="filebtn ghost small">
      Subir .md / .txt
      <input type="file" accept=".md,.txt,.markdown,.text" onchange={(e) => readFile(e.currentTarget.files?.[0])} hidden />
    </label>
    {#if fileName}<span class="fname mono">{fileName}</span>{/if}
    <span class="spacer"></span>
    <span class="muted count">{text.length} caracteres</span>
  </div>
</div>

<div class="row">
  <label class="field">
    <span class="muted">Estilo visual</span>
    <select bind:value={style}>
      {#each styles as s}<option value={s}>{s}</option>{/each}
    </select>
  </label>
  <label class="field grow">
    <span class="muted">Nombre (slug) — opcional</span>
    <input bind:value={slug} placeholder="se deriva del título" />
  </label>
</div>

<div class="bar">
  <button class="primary" onclick={importar} disabled={imp.busy || !text.trim() || noKey}>
    {imp.busy ? "Descomponiendo…" : "Importar → borrador"}
  </button>
  <span class="muted">La IA propone; vos editás antes de generar nada.</span>
</div>

{#if err || imp.err}<p class="error">{err || imp.err}</p>{/if}

{#if imp.busy || imp.log.length}
  <JobLog log={imp.log} />
{/if}

<style>


  .drop {
    border: 2px dashed var(--line-2); border-radius: var(--r-lg);
    padding: 10px; background: var(--card); transition: border-color 0.15s, background 0.15s;
  }
  /* dragging = la máquina recibe (azul); typing = el humano escribe (rojo) */
  .drop.dragging { border-color: var(--blue); background: var(--blue-wash, #eef3fb); }
  .drop:focus-within:not(.dragging) { border-color: var(--red); border-style: solid; }
  .drop textarea {
    width: 100%; border: none; resize: vertical; font-size: 15px; line-height: 1.55;
    background: transparent; padding: 8px 10px;
  }
  .drop textarea:focus { outline: none; box-shadow: none; }
  .drop-foot { display: flex; align-items: center; gap: 10px; padding: 6px 8px 2px; border-top: 1px solid var(--line); }
  .filebtn { cursor: pointer; }
  .fname { font-size: 12px; color: var(--ink-soft); }
  .spacer { flex: 1; }
  .count { font-size: 12px; }

  .row { margin: 16px 0 4px; display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end; }
  .field { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
  .field.grow { flex: 1; min-width: 200px; }
  .field input { font-family: var(--font-mono); }
  .field select { min-width: 140px; }

  .bar { margin-top: 18px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
</style>
