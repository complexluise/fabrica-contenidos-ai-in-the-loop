<script>
  // [D-080] El Inicio proyecta el bucle REAL, derivado de STAGES + stepDone (la
  // fuente unica es el motor, D-032).
  // [D-086] La jerarquia: Guion -> Storyboard (el centro) -> Producir, y las
  // mesas que NUTREN el Storyboard (Casting/Encuadres/Animatic) agrupadas debajo.
  import { studio, goTo, nextStep, stepDone, refreshStatus, TOPLEVEL, FEEDERS } from "../lib/studio.svelte.js";
  import { onMount } from "svelte";
  import StageNode from "../components/StageNode.svelte";
  import WarnStrip from "../components/WarnStrip.svelte";

  let st = $derived(studio.status);
  let next = $derived(nextStep(st));
  let project = $derived(studio.projects.find((p) => p.slug === studio.slug) || null);

  onMount(refreshStatus);

  // El bucle numerado, sin Inicio (Guion · Storyboard · Producir). Las mesas que
  // nutren el Storyboard se muestran aparte (FEEDERS). "done" lo decide el motor.
  let stations = $derived(TOPLEVEL.filter((s) => s.id !== "inicio"));

  function detail(id) {
    if (!st) return "—";
    if (id === "importar") return "borrador creado";
    if (id === "storyboard")
      return st.storyboard?.signed ? "plan firmado" : `${st.scenes_total} escenas · sin firmar`;
    if (id === "casting") {
      const c = st.casting || {};
      return c.needed > 0 ? `caras ${c.chosen}/${c.needed}` : "sin personajes con diseño";
    }
    if (id === "encuadres") {
      const k = st.keyframes || {};
      return `elegidos ${k.chosen}/${k.total}`;
    }
    if (id === "animatic") {
      const a = st.animatic;
      if (!a || !a.total) return "sin planos todavía";
      const extra = a.missing_poses > 0 ? ` · faltan ${a.missing_poses} poses` : "";
      return `planos listos ${a.ready}/${a.total}${extra}`;
    }
    if (id === "producir")
      return !st.render?.done ? "sin render" : !st.export?.done ? "video listo · falta paquete" : "video + paquete";
    return "";
  }

  const actorBadge = { tu: ["red", "vos decidís"], ia: ["blue", "la IA hace"], lee: ["", ""] };
</script>

<header class="hero">
  <div class="eyebrow">El bucle · AI-in-the-Loop</div>
  <h1>{project?.title || studio.slug}</h1>
  <p class="manifesto">
    La IA <b class="b">propone</b>. La persona <b class="r">decide</b>.
    Y la IA es solo <i>una</i> de las herramientas.
  </p>
</header>

{#if st && !st.keys?.fal_key}
  <WarnStrip actionLabel="Ir a Configuración →" onaction={() => goTo("ajustes")}>
    <b>Primero: configurá tus claves.</b> Sin la clave de fal.ai no se puede generar nada.
  </WarnStrip>
{/if}

<!-- siguiente paso: una sola recomendacion grande -->
{#if next}
  <button class="next card" onclick={() => goTo(next.tab)}>
    <div class="next-l">
      <div class="eyebrow">Tu siguiente paso</div>
      <h2>{next.label}</h2>
      <p class="muted">{next.why}</p>
    </div>
    <div class="next-go" aria-hidden="true">→</div>
  </button>
{:else if st}
  <div class="done card">
    <div class="done-l">
      <div class="eyebrow" style="color:var(--ok)">Bucle completo</div>
      <h2>Está todo listo ✓</h2>
      <p class="muted">Generaste, elegiste, renderizaste y empaquetaste. Buen trabajo.</p>
      <button class="ghost small" onclick={() => goTo("producir")}>Ver / re-armar el paquete</button>
    </div>
    {#if st.render?.final_url}
      <video class="preview" src={st.render.final_url} controls playsinline>
        <track kind="captions" />
      </video>
    {/if}
  </div>
{/if}

<!-- el bucle: Guion -> Storyboard (el centro) -> Producir (D-086) -->
<div class="eyebrow stations-h">El recorrido</div>
<div class="stations">
  {#each stations as s (s.id)}
    {@const done = stepDone(s.id, st)}
    {@const [tone, who] = actorBadge[s.actor] || ["", ""]}
    <button class="station" class:done class:next={next && next.tab === s.id && !done}
            onclick={() => goTo(s.id)}>
      <div class="st-top">
        <StageNode n={s.n} actor={s.actor} {done} size={28} />
        {#if tone}<span class="badge {tone}">{who}</span>{/if}
      </div>
      <h3>{s.label}</h3>
      <p class="desc">{s.sub}</p>
      <div class="st-foot mono">{detail(s.id)}</div>
    </button>
  {/each}
</div>

<!-- D-086: las mesas que NUTREN el Storyboard -->
<div class="eyebrow stations-h feeders-h">Nutren el storyboard</div>
<div class="stations feeders">
  {#each FEEDERS as s (s.id)}
    {@const done = stepDone(s.id, st)}
    <button class="station feeder" class:done class:next={next && next.tab === s.id && !done}
            onclick={() => goTo(s.id)}>
      <div class="st-top">
        <span class="feeder-dot actor-{s.actor}" class:done></span>
        <span class="badge red">vos decidís</span>
      </div>
      <h3>{s.label}</h3>
      <p class="desc">{s.sub}</p>
      <div class="st-foot mono">{detail(s.id)}</div>
    </button>
  {/each}
</div>

<style>
  .hero { margin-bottom: 26px; }
  .hero h1 { margin: 6px 0 10px; }
  .manifesto { font-family: var(--font-display); font-size: 19px; color: var(--ink-2); max-width: 40ch; line-height: 1.35; }
  .manifesto .b { color: var(--blue-deep); font-style: normal; }
  .manifesto .r { color: var(--red-deep); font-style: normal; }
  .manifesto i { color: var(--ink); }


  /* siguiente paso */
  .next {
    display: flex; align-items: center; gap: 20px; width: 100%; text-align: left;
    padding: 24px 28px; border-color: var(--red); border-width: 2px;
    background: linear-gradient(180deg, var(--card), var(--red-wash) 280%);
  }
  .next:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
  .next-l h2 { margin: 4px 0 4px; color: var(--red-deep); }
  .next-go { margin-left: auto; font-size: 40px; color: var(--red); font-weight: 700; }

  .done { display: flex; gap: 24px; align-items: center; padding: 24px 28px; border-color: var(--ok); }
  .done-l h2 { margin: 4px 0 6px; }
  .done-l { flex: 1; }
  .preview { width: 200px; border-radius: var(--r); border: 1px solid var(--line); background: #000; }

  .stations-h { margin: 34px 0 12px; display: block; }
  .stations { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
  .station {
    text-align: left; display: flex; flex-direction: column; gap: 7px;
    padding: 16px 17px; background: var(--card); border: 1.5px solid var(--line);
    border-radius: var(--r-lg);
  }
  .station:hover { box-shadow: var(--shadow); transform: translateY(-2px); border-color: var(--line-2); }
  .station.next { border-color: var(--red); }
  .station.done { background: linear-gradient(180deg, var(--card), var(--ok-wash) 320%); }
  .st-top { display: flex; align-items: center; justify-content: space-between; }
  .station h3 { margin: 2px 0 0; }
  .desc { font-size: 13px; color: var(--ink-2); margin: 0; min-height: 2.6em; }
  .st-foot { font-size: 12px; color: var(--ink-soft); border-top: 1px dashed var(--line); padding-top: 8px; }

  /* D-086: las mesas que nutren el Storyboard — sub-cards, anidadas visualmente */
  .feeders-h { margin-top: 18px; color: var(--ink-soft); }
  .stations.feeders { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); margin-left: 18px; border-left: 2px solid var(--line-2); padding-left: 16px; }
  .station.feeder { padding: 12px 14px; }
  .station.feeder h3 { font-size: 15px; }
  .feeder-dot { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--red); background: var(--paper); }
  .feeder-dot.done { background: var(--ok); border-color: var(--ok); }

</style>
