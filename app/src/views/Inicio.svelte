<script>
  import { studio, goTo, nextStep, stepDone, refreshStatus } from "../lib/studio.svelte.js";
  import { onMount } from "svelte";

  let st = $derived(studio.status);
  let next = $derived(nextStep(st));
  let project = $derived(studio.projects.find((p) => p.slug === studio.slug) || null);

  onMount(refreshStatus);

  // estado por estacion: `done` lo decide el motor (stepDone sobre status.stage);
  // el `detail` (X/Y) es presentacion, lee los contadores del status.
  function station(id) {
    if (!st) return { done: false, detail: "—", actor: "tu" };
    const done = stepDone(id, st);
    if (id === "importar") {
      const d = stepDone(id, st);
      return { done: d, detail: d ? "plan firmado" : "proyecto creado, sin firmar", actor: "ia" };
    }
    if (id === "storyboard")
      return {
        done: !!st.storyboard?.signed,
        detail: st.storyboard?.signed ? "plan firmado" : `${st.scenes_total} escenas · sin firmar`,
        actor: "tu",
      };
    if (id === "elegir") {
      const c = st.casting || {}, k = st.keyframes || {};
      const parts = [];
      if (c.needed > 0) parts.push(`casting ${c.chosen}/${c.needed}`);
      parts.push(`encuadres ${k.chosen}/${k.total}`);
      return { done, detail: parts.join(" · "), actor: "tu" };
    }
    if (id === "producir") {
      const detail = !st.render?.done ? "sin render" : !st.export?.done ? "falta paquete" : "video + paquete";
      return { done, detail, actor: "ia" };
    }
    return { done: false, detail: "", actor: "tu" };
  }

  const STATIONS = [
    { id: "importar",   n: 1, label: "Importar",   desc: "Pegá un texto; la IA arma el borrador." },
    { id: "storyboard", n: 2, label: "Storyboard", desc: "Editá y firmá el plan, plano a plano." },
    { id: "elegir",     n: 3, label: "Elegir",     desc: "La IA genera opciones; vos elegís." },
    { id: "producir",   n: 4, label: "Producir",   desc: "Se arma el video y el paquete." },
  ];

  const actorBadge = { tu: ["red", "vos decidís"], ia: ["blue", "la IA hace"], lee: ["", "leer"] };
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
  <div class="warn-strip">
    <b>Primero: configurá tus claves.</b> Sin la clave de fal.ai no se puede generar nada.
    <button class="small" onclick={() => goTo("ajustes")}>Ir a Configuración →</button>
  </div>
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

<!-- el bucle, estacion por estacion -->
<div class="eyebrow stations-h">El recorrido completo</div>
<div class="stations">
  {#each STATIONS as s}
    {@const stt = station(s.id)}
    {@const [tone, who] = actorBadge[stt.actor]}
    <button class="station" class:done={stt.done} class:next={next && next.tab === s.id} onclick={() => goTo(s.id)}>
      <div class="st-top">
        <span class="num actor-{stt.actor}">{stt.done ? "✓" : s.n}</span>
        {#if tone}<span class="badge {tone}">{who}</span>{/if}
      </div>
      <h3>{s.label}</h3>
      <p class="desc">{s.desc}</p>
      <div class="st-foot mono">{stt.detail}</div>
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

  .warn-strip {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--warn-wash); border: 1.5px solid #e0c089; color: #6b4a12;
    border-radius: var(--r); padding: 12px 16px; margin-bottom: 22px;
  }
  .warn-strip button { margin-left: auto; }

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
  .num {
    width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
    font-family: var(--font-mono); font-weight: 700; font-size: 13px;
    border: 2px solid var(--line-2); color: var(--ink-soft); background: var(--paper);
  }
  .num.actor-tu { border-color: var(--red); color: var(--red-deep); }
  .num.actor-ia { border-color: var(--blue); color: var(--blue-deep); }
  .station.done .num { background: var(--ok); border-color: var(--ok); color: #fff; }
  .station h3 { margin: 2px 0 0; }
  .desc { font-size: 13px; color: var(--ink-2); margin: 0; min-height: 2.6em; }
  .st-foot { font-size: 12px; color: var(--ink-soft); border-top: 1px dashed var(--line); padding-top: 8px; }

  .muted { color: var(--ink-soft); }
</style>
