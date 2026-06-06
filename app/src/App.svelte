<script>
  import { onMount } from "svelte";
  import { studio, STAGES, loadProjects, setSlug, goTo, nextStep, hasProject } from "./lib/studio.svelte.js";
  import Inicio from "./views/Inicio.svelte";
  import Importar from "./views/Importar.svelte";
  import Storyboard from "./views/Storyboard.svelte";
  import Picker from "./views/Picker.svelte";
  import Produccion from "./views/Produccion.svelte";
  import Ajustes from "./views/Ajustes.svelte";

  let current = $derived(studio.projects.find((p) => p.slug === studio.slug) || null);
  let next = $derived(nextStep(studio.status));

  onMount(loadProjects);

  // Estado de cada paso del bucle para la espina lateral.
  function stageState(id) {
    const st = studio.status;
    if (id === "inicio") return "info";
    if (id === "importar") return hasProject() ? "done" : "todo";
    if (id === "storyboard") return hasProject() ? "info" : "todo";
    if (!st) return "todo";
    if (id === "ajustes") return st.keys?.fal_key ? "done" : "todo";
    if (id === "elegir") {
      const cast = st.casting || {}, kf = st.keyframes || {};
      const castOk = cast.needed === 0 || cast.chosen >= cast.needed;
      const kfOk = kf.total > 0 && kf.chosen >= kf.total;
      return castOk && kfOk ? "done" : "todo";
    }
    if (id === "producir") return st.render?.done && st.export?.done ? "done" : "todo";
    return "todo";
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
      <div class="eyebrow">Proyecto</div>
      <div class="select-wrap">
        <select value={studio.slug} onchange={(e) => setSlug(e.currentTarget.value)}>
          {#each studio.projects as p}
            <option value={p.slug}>{p.title}</option>
          {/each}
        </select>
      </div>
      {#if current}
        <div class="pmeta">{current.style} · {current.scenes} escena{current.scenes === 1 ? "" : "s"}</div>
      {/if}
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
  .select-wrap select { width: 100%; font-size: 15px; font-weight: 600; font-family: var(--font-display); }
  .pmeta { font-size: 12px; color: var(--ink-soft); }

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

  .foot { margin-top: auto; }
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
