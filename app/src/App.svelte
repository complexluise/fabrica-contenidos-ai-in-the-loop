<script>
  import { onMount } from "svelte";
  import { get } from "./lib/api.js";
  import Guion from "./views/Guion.svelte";
  import Picker from "./views/Picker.svelte";
  import Produccion from "./views/Produccion.svelte";
  import Ajustes from "./views/Ajustes.svelte";

  let projects = $state([]);
  let slug = $state("");
  let tab = $state("guion");
  let error = $state("");

  const nav = [
    ["guion", "📝", "Guion"],
    ["picker", "🖼️", "Picker"],
    ["prod", "🎬", "Render / Export"],
    ["ajustes", "⚙️", "Ajustes"],
  ];

  let current = $derived(projects.find((p) => p.slug === slug) || null);

  async function loadProjects() {
    try {
      projects = await get("/api/projects");
      if (!slug && projects.length) slug = projects[0].slug;
    } catch (e) {
      error = String(e);
    }
  }
  onMount(loadProjects);
</script>

<div class="layout">
  <aside class="sidebar">
    <div class="brand">🎬 Video Studio<small>local</small></div>

    <div class="project">
      <div class="label">PROYECTO</div>
      <select bind:value={slug}>
        {#each projects as p}
          <option value={p.slug}>{p.title}</option>
        {/each}
      </select>
      {#if current}
        <div class="pmeta">{current.style} · {current.scenes} escena{current.scenes === 1 ? "" : "s"}</div>
      {/if}
    </div>

    <nav>
      {#each nav as [id, icon, label]}
        <button class:active={tab === id} onclick={() => (tab = id)}>
          <span class="ico">{icon}</span>{label}
        </button>
      {/each}
    </nav>

    <div class="foot">AI-in-the-Loop · vos decidís</div>
  </aside>

  <main>
    {#if error}
      <p class="error">{error}</p>
    {:else if !slug}
      <p class="muted">No hay proyectos en <code>projects/</code>.</p>
    {:else if tab === "guion"}
      <Guion {slug} />
    {:else if tab === "picker"}
      <Picker {slug} />
    {:else if tab === "prod"}
      <Produccion {slug} />
    {:else if tab === "ajustes"}
      <Ajustes />
    {/if}
  </main>
</div>

<style>
  .layout { display: flex; min-height: 100vh; }
  .sidebar {
    width: 240px; flex-shrink: 0; background: var(--panel);
    border-right: 1px solid var(--border); display: flex; flex-direction: column;
    padding: 18px 14px; gap: 22px; position: sticky; top: 0; height: 100vh;
  }
  .brand { font-size: 17px; font-weight: 700; display: flex; align-items: baseline; gap: 8px; }
  .brand small { color: var(--muted); font-weight: 400; font-size: 12px; }

  .project { display: flex; flex-direction: column; gap: 6px; }
  .label { font-size: 11px; letter-spacing: 0.08em; color: var(--muted); font-weight: 700; }
  .project select { width: 100%; font-size: 15px; font-weight: 600; padding: 10px; }
  .pmeta { font-size: 12px; color: var(--muted); }

  nav { display: flex; flex-direction: column; gap: 4px; }
  nav button {
    display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
    background: transparent; border: 1px solid transparent; padding: 10px 12px;
  }
  nav button:hover { background: var(--panel2); border-color: var(--border); }
  nav button.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .ico { width: 20px; text-align: center; }

  .foot { margin-top: auto; font-size: 11px; color: var(--muted); }

  main { flex: 1; padding: 28px 34px; max-width: 980px; }
  .error { color: var(--bad); }
  .muted { color: var(--muted); }
  code { background: var(--panel2); padding: 1px 6px; border-radius: 4px; }
</style>
