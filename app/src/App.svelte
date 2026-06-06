<script>
  import { onMount } from "svelte";
  import { studio, STAGES, CONFIG, loadProjects, setSlug, goTo, nextStep, stepDone, hasProject,
           createProject, deleteProject } from "./lib/studio.svelte.js";
  import { get, humanError } from "./lib/api.js";
  import Inicio from "./views/Inicio.svelte";
  import Importar from "./views/Importar.svelte";
  import Storyboard from "./views/Storyboard.svelte";
  import Picker from "./views/Picker.svelte";
  import Produccion from "./views/Produccion.svelte";
  import Ajustes from "./views/Ajustes.svelte";

  let current = $derived(studio.projects.find((p) => p.slug === studio.slug) || null);
  let next = $derived(nextStep(studio.status));
  let keysOk = $derived(studio.status?.keys?.fal_key);

  // --- gestión de proyectos (#3) ---
  let styles = $state(["lego"]);
  let creating = $state(false);     // form de "nuevo" abierto
  let newTitle = $state("");
  let newStyle = $state("lego");
  let busy = $state(false);
  let pmErr = $state("");

  onMount(async () => {
    await loadProjects();
    try {
      const s = await get("/api/styles");
      if (s?.length) { styles = s; newStyle = s.includes("lego") ? "lego" : s[0]; }
    } catch { /* deja el default */ }
  });

  async function doCreate() {
    if (!newTitle.trim()) return;
    busy = true; pmErr = "";
    try {
      await createProject(newTitle.trim(), newStyle);
      creating = false; newTitle = "";
      goTo("storyboard");  // proyecto en blanco -> a armar el plan
    } catch (e) { pmErr = humanError(e); } finally { busy = false; }
  }

  async function doDelete() {
    if (!current) return;
    if (!confirm(`¿Borrar "${current.title}"? Se elimina TODO (cache, runs, export). No se puede deshacer.`)) return;
    busy = true; pmErr = "";
    try { await deleteProject(current.slug); }
    catch (e) { pmErr = humanError(e); } finally { busy = false; }
  }

  // Estado de cada paso del bucle para la espina lateral. La verdad la decide el
  // motor (status.stage); aca solo proyectamos a done/todo/info.
  function stageState(id) {
    if (id === "inicio") return "info";
    if (id === "importar") return hasProject() ? "done" : "todo";
    if (!studio.status) return "todo";
    return stepDone(id, studio.status) ? "done" : "todo";
  }
</script>

<div class="layout">
  <aside class="sidebar">
    <div class="brand">
      <svg class="loop" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 11a8 8 0 1 0-2.3 5.6" fill="none" stroke="currentColor"
              stroke-width="2.4" stroke-linecap="round" />
        <path d="M20 5v5h-5" fill="none" stroke="currentColor"
              stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <div class="brand-t">
        <strong>Taller</strong>
        <small>IA con la persona dentro</small>
      </div>
    </div>

    <div class="project">
      <div class="phead">
        <span class="eyebrow">Proyecto</span>
        <button class="mini" title="Nuevo proyecto" onclick={() => (creating = !creating)}>＋ Nuevo</button>
      </div>

      {#if creating}
        <div class="create">
          <input placeholder="Título del proyecto" bind:value={newTitle}
                 onkeydown={(e) => e.key === "Enter" && doCreate()} />
          <select bind:value={newStyle}>
            {#each styles as s}<option value={s}>{s}</option>{/each}
          </select>
          <div class="create-actions">
            <button class="primary small" onclick={doCreate} disabled={busy || !newTitle.trim()}>Crear</button>
            <button class="ghost small" onclick={() => (creating = false)}>Cancelar</button>
          </div>
        </div>
      {/if}

      <div class="select-wrap">
        <select value={studio.slug} onchange={(e) => setSlug(e.currentTarget.value)}>
          {#if !studio.projects.length}<option value="">(sin proyectos)</option>{/if}
          {#each studio.projects as p}
            <option value={p.slug}>{p.title}</option>
          {/each}
        </select>
        {#if current}
          <button class="mini danger" title="Borrar proyecto" onclick={doDelete} disabled={busy}>🗑</button>
        {/if}
      </div>
      {#if current}
        <div class="pmeta">{current.style} · {current.scenes} escena{current.scenes === 1 ? "" : "s"}</div>
      {/if}
      {#if pmErr}<div class="pm-err">{pmErr}</div>{/if}
    </div>

    <nav class="spine">
      {#each STAGES as s, i}
        {@const state = stageState(s.id)}
        {@const isCurrent = next && next.tab === s.id && studio.tab !== s.id}
        <button
          class="step actor-{s.actor} state-{state}"
          class:active={studio.tab === s.id}
          class:current={isCurrent}
          onclick={() => goTo(s.id)}
        >
          {#if i > 0}<span class="rail" class:last={i === STAGES.length - 1}></span>{/if}
          <span class="node">
            {#if state === "done"}
              <svg viewBox="0 0 16 16" class="tick"><path d="M3 8.5l3.2 3L13 4.5"
                fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"
                stroke-linejoin="round"/></svg>
            {:else if s.id === "inicio"}
              <svg viewBox="0 0 16 16" class="home"><path d="M2.5 7.5L8 3l5.5 4.5V13a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1z"
                fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
            {:else}
              {s.n}
            {/if}
          </span>
          <span class="txt">
            <span class="lbl">{s.label}</span>
            <span class="sub">{s.sub}</span>
          </span>
        </button>
      {/each}
    </nav>

    <div class="foot">
      <button class="config" class:active={studio.tab === CONFIG.id} class:warn={!keysOk}
              onclick={() => goTo(CONFIG.id)}>
        <svg viewBox="0 0 24 24" class="gear" aria-hidden="true">
          <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z" fill="none" stroke="currentColor" stroke-width="1.8"/>
          <path d="M19.4 13a7.7 7.7 0 0 0 0-2l2-1.5-2-3.4-2.3 1a7.7 7.7 0 0 0-1.7-1l-.3-2.5H10.9l-.3 2.5a7.7 7.7 0 0 0-1.7 1l-2.3-1-2 3.4L4.6 11a7.7 7.7 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7.7 7.7 0 0 0 1.7 1l.3 2.5h3.2l.3-2.5a7.7 7.7 0 0 0 1.7-1l2.3 1 2-3.4z"
            fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
        </svg>
        <span class="txt">
          <span class="lbl">{CONFIG.label}</span>
          <span class="sub">{keysOk ? "claves listas" : "faltan claves"}</span>
        </span>
        {#if !keysOk}<span class="badge-warn">!</span>{/if}
      </button>

      <div class="legend">
        <span><i class="dot blue"></i> la IA propone</span>
        <span><i class="dot red"></i> vos decidís</span>
      </div>
    </div>
  </aside>

  <main>
    {#if studio.error}
      <p class="error">{studio.error}</p>
    {:else if studio.tab === "importar"}
      <Importar />
    {:else if studio.tab === "ajustes"}
      <Ajustes />
    {:else if !studio.slug}
      <div class="empty card">
        <h2>No hay proyectos todavía</h2>
        <p class="muted">Empezá importando un guion: pegá o subí tu texto y la IA arma el borrador.</p>
        <button class="primary" onclick={() => goTo("importar")}>Importar un guion →</button>
      </div>
    {:else if studio.tab === "inicio"}
      <Inicio />
    {:else if studio.tab === "storyboard"}
      <Storyboard slug={studio.slug} />
    {:else if studio.tab === "elegir"}
      <Picker slug={studio.slug} />
    {:else if studio.tab === "producir"}
      <Produccion slug={studio.slug} />
    {/if}
  </main>
</div>

<style>
  .layout { display: flex; min-height: 100vh; }

  /* --- sidebar --- */
  .sidebar {
    width: 274px;
    flex-shrink: 0;
    background: var(--paper-2);
    border-right: 1.5px solid var(--line-2);
    display: flex;
    flex-direction: column;
    padding: 22px 18px;
    gap: 26px;
    position: sticky;
    top: 0;
    height: 100vh;
  }

  .brand { display: flex; align-items: center; gap: 11px; }
  .brand .loop { width: 30px; height: 30px; color: var(--red); flex-shrink: 0; }
  .brand-t { display: flex; flex-direction: column; line-height: 1.1; }
  .brand-t strong { font-family: var(--font-display); font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
  .brand-t small { color: var(--ink-soft); font-size: 11.5px; }

  .project { display: flex; flex-direction: column; gap: 7px; }
  .phead { display: flex; align-items: center; justify-content: space-between; }
  .mini {
    background: transparent; border: 1px solid var(--line-2); border-radius: var(--r-sm);
    padding: 2px 8px; font-size: 11.5px; font-weight: 700; color: var(--ink-soft); box-shadow: none;
  }
  .mini:hover { background: var(--card); color: var(--ink); box-shadow: none; }
  .mini.danger { flex-shrink: 0; padding: 2px 7px; }
  .mini.danger:hover { color: var(--red-deep); border-color: var(--red); background: var(--red-wash); }
  .select-wrap { display: flex; align-items: center; gap: 6px; }
  .select-wrap select { flex: 1; min-width: 0; font-size: 15px; font-weight: 600; font-family: var(--font-display); }
  .pmeta { font-size: 12px; color: var(--ink-soft); }
  .create { display: flex; flex-direction: column; gap: 6px; padding: 9px; background: var(--card); border: 1px solid var(--line-2); border-radius: var(--r); }
  .create input, .create select { width: 100%; font-size: 13px; }
  .create-actions { display: flex; gap: 6px; }
  .pm-err { font-size: 11.5px; color: var(--red-deep); }

  /* --- la espina del bucle --- */
  .spine { display: flex; flex-direction: column; }
  .step {
    position: relative;
    display: flex;
    align-items: center;
    gap: 13px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    border-radius: var(--r);
    padding: 9px 11px 9px 9px;
    box-shadow: none;
  }
  .step:hover { background: rgba(33, 28, 22, 0.05); box-shadow: none; }
  .step.active { background: var(--card); box-shadow: var(--shadow); }

  /* riel vertical que conecta los nodos (el "bucle") */
  .rail {
    position: absolute;
    left: 27px;
    top: -10px;
    width: 2px;
    height: 18px;
    background: var(--line-2);
  }

  .node {
    position: relative;
    z-index: 1;
    width: 30px;
    height: 30px;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border-radius: 50%;
    border: 2px solid var(--line-2);
    background: var(--paper);
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 700;
    color: var(--ink-soft);
  }
  .tick, .home { width: 16px; height: 16px; }

  /* color por actor (quien decide en ese paso) */
  .step.actor-tu .node  { border-color: var(--red);  color: var(--red-deep); }
  .step.actor-ia .node  { border-color: var(--blue); color: var(--blue-deep); }

  /* hecho = relleno */
  .step.state-done .node { background: var(--ok); border-color: var(--ok); color: #fff; }

  /* paso actual = anillo pulsante */
  .step.current .node { animation: pulse 1.8s ease-in-out infinite; }
  .step.current .lbl::after {
    content: "siguiente";
    margin-left: 8px;
    font-family: var(--font-sans);
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--red);
    background: var(--red-wash);
    padding: 1px 6px;
    border-radius: 999px;
    vertical-align: middle;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(214, 64, 42, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(214, 64, 42, 0); }
  }

  .txt { display: flex; flex-direction: column; line-height: 1.15; min-width: 0; }
  .lbl { font-weight: 700; font-size: 14.5px; }
  .sub { font-size: 11.5px; color: var(--ink-soft); }
  .step.active .lbl { color: var(--ink); }

  .foot { margin-top: auto; display: flex; flex-direction: column; gap: 14px; }

  .config {
    position: relative; display: flex; align-items: center; gap: 11px; width: 100%;
    text-align: left; background: transparent; border: 1px solid var(--line-2);
    border-radius: var(--r); padding: 9px 11px; box-shadow: none;
  }
  .config:hover { background: rgba(33, 28, 22, 0.05); box-shadow: none; }
  .config.active { background: var(--card); box-shadow: var(--shadow); }
  .config.warn { border-color: var(--red); }
  .config .gear { width: 22px; height: 22px; color: var(--ink-soft); flex-shrink: 0; }
  .config .lbl { font-weight: 700; font-size: 13.5px; }
  .config .sub { font-size: 11px; color: var(--ink-soft); }
  .config.warn .sub { color: var(--red-deep); }
  .badge-warn {
    margin-left: auto; width: 18px; height: 18px; border-radius: 50%; background: var(--red);
    color: #fff; font-weight: 700; font-size: 12px; display: grid; place-items: center;
  }

  .legend { display: flex; flex-direction: column; gap: 5px; font-size: 11.5px; color: var(--ink-soft); }
  .legend span { display: flex; align-items: center; gap: 7px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .dot.red { background: var(--red); }
  .dot.blue { background: var(--blue); }

  /* --- main --- */
  main { flex: 1; padding: 42px 48px 80px; max-width: 1080px; }
  .empty { padding: 40px; text-align: center; }

  @media (max-width: 760px) {
    .layout { flex-direction: column; }
    .sidebar { width: auto; height: auto; position: static; }
    main { padding: 28px 22px 60px; }
  }
</style>
