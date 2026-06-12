<script>
  import { onMount } from "svelte";
  import { get, runJob, humanError } from "../lib/api.js";
  import { studio, goTo, loadProjects, setSlug } from "../lib/studio.svelte.js";

  let text = $state("");
  let slug = $state("");
  let style = $state("lego");
  let styles = $state(["lego"]);
  let fileName = $state("");
  let dragging = $state(false);
  let busy = $state(false);
  let log = $state([]);
  let err = $state("");

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

  async function importar() {
    err = "";
    log = [];
    if (!text.trim()) {
      err = "Pegá o subí un texto primero.";
      return;
    }
    busy = true;
    runJob("/api/projects/import", {
      body: { text, slug: slug.trim() || undefined, style },
      onLine: (l) => (log = [...log, l]),
      onDone: async (status, jobId) => {
        busy = false;
        if (status !== "done") {
          err = "La importación falló. Revisá el detalle de arriba.";
          return;
        }
        const detail = await get(`/api/jobs/${jobId}`);
        const newSlug = detail.result?.slug;
        await loadProjects();
        if (newSlug) {
          await setSlug(newSlug);
          goTo("storyboard"); // a editar el borrador propuesto
        }
      },
      onError: (e) => {
        busy = false;
        err = humanError(e);
      },
    });
  }
</script>

<header class="head">
  <div class="eyebrow">Paso 1 · la IA propone</div>
  <h1>Importar un guion</h1>
  <p class="lede muted">
    Pegá o subí tu texto. La IA lo descompone en un <b>borrador</b> de proyecto
    (título, sinopsis y escenas); después lo editás y firmás en el Storyboard.
  </p>
</header>

{#if noKey}
  <div class="warn-strip">
    <b>Falta la clave de Anthropic.</b> La descomposición usa Claude.
    <button class="small" onclick={() => goTo("ajustes")}>Ir a Ajustes →</button>
  </div>
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
  <button class="primary" onclick={importar} disabled={busy || !text.trim() || noKey}>
    {busy ? "Descomponiendo…" : "Importar → borrador"}
  </button>
  <span class="muted">La IA propone; vos editás antes de generar nada.</span>
</div>

{#if err}<p class="error">{err}</p>{/if}

{#if log.length}
  <pre class="log">{log.join("\n")}</pre>
{/if}

<style>
  .head { margin-bottom: 16px; }
  .head h1 { margin: 5px 0 6px; }
  .lede { font-size: 16px; max-width: 64ch; }

  .warn-strip {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--warn-wash); border: 1.5px solid #e0c089; color: #6b4a12;
    border-radius: var(--r); padding: 12px 16px; margin-bottom: 18px;
  }
  .warn-strip button { margin-left: auto; }

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
  .muted { color: var(--ink-soft); }
  .log {
    margin-top: 16px; background: #1c1814; color: #e8e2d8; border-radius: var(--r);
    padding: 14px 16px; font-size: 12.5px; line-height: 1.55; max-height: 280px; overflow: auto;
    white-space: pre-wrap;
  }
</style>
