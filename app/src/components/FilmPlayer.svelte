<script>
  // [D-087] El player de la película en stills — una sola implementación,
  // usada por el Storyboard (con narrativa: ver qué pasa) y por el Animatic
  // (revisar poses). Reproduce cada plano por su duración.
  //
  // Fix "falta pose" (D-070): solo los planos `aterriza` CON apertura hacen las
  // dos fases (apertura 40% -> destino 60%); los cámara-actúa muestran su destino
  // toda la duración (antes mostraban "falta pose" el primer 40%). Un plano sin
  // imagen real muestra un aviso accionable, no un hueco mudo.
  import { onMount, onDestroy } from "svelte";

  let { frames = [], onclose } = $props();

  let idx = $state(0);
  let phase = $state("start");   // "start" | "destino"
  let timer = null;

  let f = $derived(frames[idx] ?? null);
  let hasOpening = $derived(!!(f && f.lands && f.start));
  let img = $derived(!f ? null : (phase === "start" && hasOpening ? f.start : f.destino));

  function clear() { if (timer) { clearTimeout(timer); timer = null; } }
  function close() { clear(); onclose?.(); }

  function step() {
    const cur = frames[idx];
    if (!cur) { close(); return; }
    const dur = Math.max(1, cur.duration_s || 2) * 1000;
    const opening = !!(cur.lands && cur.start);
    if (phase === "start" && opening) {
      timer = setTimeout(() => { phase = "destino"; step(); }, dur * 0.4);
    } else {
      const remaining = (phase === "destino" && opening) ? dur * 0.6 : dur;
      timer = setTimeout(() => {
        if (idx + 1 < frames.length) { idx += 1; phase = "start"; step(); }
        else close();
      }, remaining);
    }
  }

  onMount(() => { if (frames.length) step(); else close(); });
  onDestroy(clear);
</script>

<svelte:window onkeydown={(e) => { if (e.key === "Escape") close(); }} />

{#if f}
  <div class="player" onclick={close} role="button" tabindex="0"
       onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); close(); } }}>
    <div class="stage" onclick={(e) => e.stopPropagation()} role="presentation">
      <div class="frame">
        {#if img}
          <img src={img} alt={f.shot_id} />
        {:else}
          <div class="hole">
            <span>Este plano aún no tiene imagen</span>
            <small>generala en Encuadres / Animatic</small>
          </div>
        {/if}
      </div>

      <div class="story">
        <div class="story-head">
          <span class="scene-id mono">{f.sceneLabel || f.shot_id}</span>
          {#if hasOpening}<span class="phase-tag">{phase === "start" ? "apertura" : "destino"}</span>{/if}
        </div>
        {#if f.action}<p class="line action">{f.action}</p>{/if}
        {#if f.intention}<p class="line intention"><span class="cue">idea</span>{f.intention}</p>{/if}
        {#if f.line}<p class="line vo"><span class="cue">voz</span>{f.line}</p>{/if}
        {#if f.caption}<p class="line cc"><span class="cue">cc</span>{f.caption}</p>{/if}
      </div>
    </div>

    <div class="bar">
      <span class="mono">{f.shot_id} · {f.duration_s}s</span>
      <span class="dots">
        {#each frames as _fr, i}<span class="dot" class:on={i === idx} class:past={i < idx}></span>{/each}
      </span>
      <span class="muted">plano {idx + 1}/{frames.length} — clic o Esc para salir</span>
    </div>
  </div>
{/if}

<style>
  .player {
    position: fixed; inset: 0; z-index: 60; background: rgba(15, 12, 9, 0.94);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 18px; cursor: pointer; padding: 24px;
  }
  .stage {
    display: flex; gap: 24px; align-items: center; max-width: 1100px; width: 100%;
    cursor: default; flex-wrap: wrap; justify-content: center;
  }
  .frame { flex: 0 1 620px; }
  .frame img { width: 100%; max-height: 70vh; object-fit: contain; border-radius: var(--r); box-shadow: 0 12px 60px rgba(0,0,0,0.6); display: block; }
  .hole {
    width: 100%; aspect-ratio: 16/9; display: flex; flex-direction: column; gap: 6px;
    align-items: center; justify-content: center; border-radius: var(--r);
    border: 1.5px dashed rgba(255,255,255,0.25); color: #cbb; text-align: center;
  }
  .hole span { font-size: 15px; } .hole small { font-size: 12px; color: #998; }

  .story { flex: 1 1 280px; min-width: 240px; color: #ece3d2; display: flex; flex-direction: column; gap: 9px; }
  .story-head { display: flex; align-items: center; gap: 10px; }
  .scene-id { font-family: var(--font-mono); font-size: 15px; color: #fff; }
  .phase-tag {
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: #f0d8c0; background: rgba(214,64,42,0.35); border-radius: 999px; padding: 1px 8px;
  }
  .line { margin: 0; font-size: 14px; line-height: 1.5; display: flex; gap: 8px; align-items: baseline; }
  .line.action { font-size: 16px; font-family: var(--font-display); color: #fff; }
  .line.intention { font-style: italic; color: #c9bfaf; }
  .line.vo { color: #e7dcc6; }
  .line.cc { color: #bcae93; }
  .cue { font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #9a8e76; min-width: 24px; }

  .bar { display: flex; align-items: center; gap: 16px; color: #ddd; font-size: 13px; flex-wrap: wrap; justify-content: center; }
  .bar .mono { font-family: var(--font-mono); }
  .dots { display: flex; gap: 4px; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,0.25); }
  .dot.past { background: rgba(255,255,255,0.5); }
  .dot.on { background: var(--red); transform: scale(1.4); }
</style>
