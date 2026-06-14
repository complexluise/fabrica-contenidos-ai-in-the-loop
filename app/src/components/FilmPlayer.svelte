<script>
  // [D-087] El player de la película en stills — una sola implementación,
  // usada por el Storyboard (con narrativa: ver qué pasa) y por el Animatic
  // (revisar poses). Reproduce cada plano por su duración.
  //
  // Fix "falta pose" (D-070): solo los planos `aterriza` CON apertura hacen las
  // dos fases (apertura 40% -> destino 60%); los cámara-actúa muestran su destino
  // toda la duración (antes mostraban "falta pose" el primer 40%). Un plano sin
  // imagen real muestra un aviso accionable, no un hueco mudo.
  //
  // Prop `start` (D-094): índice inicial para reproducir desde un plano específico
  // (la tira temporal del Storyboard pasa el índice del bloque clickeado).
  import { onMount, onDestroy } from "svelte";

  let { frames = [], onclose, start = 0 } = $props();

  // idx arranca en 0 y se ajusta al start prop en onMount (evita warning Svelte 5
  // por captura temprana de props en $state — el valor inicial es correcto porque
  // el Storyboard usa {#key playerStart} para re-montar el componente).
  let idx = $state(0);
  let phase = $state("start");   // "start" | "destino"
  let timer = null;
  // Para el scrubber: acumula segundos hasta el plano actual
  let elapsed = $state(0);

  let f = $derived(frames[idx] ?? null);
  let hasOpening = $derived(!!(f && f.lands && f.start));
  let img = $derived(!f ? null : (phase === "start" && hasOpening ? f.start : f.destino));

  // Duración total de la película en segundos
  let totalDur = $derived(frames.reduce((a, fr) => a + Math.max(1, fr.duration_s || 2), 0));

  // Offset de tiempo de cada plano (acumulado desde el inicio)
  let frameOffsets = $derived((() => {
    const offsets = [];
    let acc = 0;
    for (const fr of frames) {
      offsets.push(acc);
      acc += Math.max(1, fr.duration_s || 2);
    }
    return offsets;
  })());

  // Progreso del scrubber: 0..1
  let progress = $derived(totalDur > 0 ? (elapsed + (idx < frameOffsets.length ? frameOffsets[idx] : 0)) / totalDur : 0);

  function clear() { if (timer) { clearTimeout(timer); timer = null; } }
  function close() { clear(); onclose?.(); }

  function jumpTo(newIdx) {
    if (newIdx < 0 || newIdx >= frames.length) return;
    clear();
    idx = newIdx;
    phase = "start";
    elapsed = 0;
    step();
  }

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
        if (idx + 1 < frames.length) { idx += 1; phase = "start"; elapsed = 0; step(); }
        else close();
      }, remaining);
    }
  }

  // Navegar con teclado izq/der dentro del player
  function handleKey(e) {
    if (e.key === "Escape") { close(); return; }
    if (e.key === "ArrowLeft") { e.preventDefault(); jumpTo(idx - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); jumpTo(idx + 1); }
  }

  // Click en el scrubber: saltar al plano correspondiente
  function scrubClick(e) {
    e.stopPropagation();
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetTime = ratio * totalDur;
    // Encontrar qué plano corresponde a ese tiempo
    let target = 0;
    for (let i = 0; i < frames.length; i++) {
      const end = frameOffsets[i] + Math.max(1, frames[i].duration_s || 2);
      if (targetTime <= end || i === frames.length - 1) { target = i; break; }
    }
    jumpTo(target);
  }

  onMount(() => {
    // Aplicar el índice inicial (prop start) ahora que el componente está montado.
    // El Storyboard usa {#key playerStart} para garantizar re-mount en cada cambio.
    idx = Math.max(0, Math.min(start, frames.length - 1));
    if (frames.length) step(); else close();
  });
  onDestroy(clear);
</script>

<svelte:window onkeydown={handleKey} />

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

    <!-- Scrubber + controles de navegación -->
    <div class="bar" onclick={(e) => e.stopPropagation()} role="presentation">
      <span class="mono bar-info">{f.shot_id} · {f.duration_s}s</span>

      <!-- Barra de progreso clicable (scrubber) -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div class="scrubber-wrap" role="slider" aria-label="Progreso de la película"
           aria-valuemin="0" aria-valuemax={frames.length - 1} aria-valuenow={idx}
           tabindex="0"
           onclick={scrubClick}
           onkeydown={(e) => {
             // stopPropagation: el slider enfocado maneja las flechas; sin esto
             // tambien las atrapa el <svelte:window> y saltaria 2 planos.
             if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); jumpTo(idx - 1); }
             if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); jumpTo(idx + 1); }
           }}>
        {#each frames as fr, i}
          {@const w = totalDur > 0 ? (Math.max(1, fr.duration_s || 2) / totalDur) * 100 : (100 / frames.length)}
          <button
            class="scrub-seg"
            class:past={i < idx}
            class:on={i === idx}
            style="width:{w}%"
            title="{fr.shot_id} — {fr.duration_s}s"
            onclick={(e) => { e.stopPropagation(); jumpTo(i); }}
            tabindex="-1"
            aria-label="Ir al plano {i + 1}: {fr.shot_id}"
          ></button>
        {/each}
        <div class="scrub-head" style="left:{Math.min(progress * 100, 100)}%"></div>
      </div>

      <!-- Botones prev/next -->
      <div class="nav-btns">
        <button class="nav-btn" onclick={() => jumpTo(idx - 1)} disabled={idx === 0}
                title="Plano anterior (tecla izquierda)" aria-label="Plano anterior">
          &lsaquo;
        </button>
        <span class="nav-count mono">{idx + 1}/{frames.length}</span>
        <button class="nav-btn" onclick={() => jumpTo(idx + 1)} disabled={idx === frames.length - 1}
                title="Plano siguiente (tecla derecha)" aria-label="Plano siguiente">
          &rsaquo;
        </button>
      </div>

      <span class="muted bar-hint">clic o Esc para salir</span>
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

  /* --- Barra inferior: scrubber + navegación --- */
  .bar {
    display: flex; align-items: center; gap: 12px; color: #ddd; font-size: 13px;
    flex-wrap: wrap; justify-content: center; width: 100%; max-width: 900px;
    cursor: default;
  }
  .bar-info { font-family: var(--font-mono); flex-shrink: 0; }
  .bar-hint { flex-shrink: 0; font-size: 12px; }

  /* Scrubber proporcional */
  .scrubber-wrap {
    position: relative; flex: 1; height: 20px; display: flex; align-items: center;
    gap: 1px; cursor: pointer; min-width: 120px; border-radius: 4px;
    outline: none;
  }
  .scrubber-wrap:focus-visible { box-shadow: 0 0 0 2px rgba(214,64,42,0.7); border-radius: 4px; }

  .scrub-seg {
    height: 8px; border-radius: 2px; flex-shrink: 0; cursor: pointer;
    background: rgba(255,255,255,0.18); border: none; padding: 0;
    transition: background 0.1s, transform 0.1s;
    box-sizing: border-box;
  }
  .scrub-seg:hover { background: rgba(255,255,255,0.40); transform: scaleY(1.4); }
  .scrub-seg.past { background: rgba(255,255,255,0.50); }
  .scrub-seg.on { background: var(--red); transform: scaleY(1.3); }

  /* Cabezal de reproducción */
  .scrub-head {
    position: absolute; top: 50%; transform: translate(-50%, -50%);
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--red); box-shadow: 0 0 6px rgba(214,64,42,0.8);
    pointer-events: none; transition: left 0.08s linear;
  }

  /* Botones prev/next */
  .nav-btns {
    display: flex; align-items: center; gap: 6px; flex-shrink: 0;
  }
  .nav-btn {
    width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.3);
    background: rgba(255,255,255,0.08); color: #fff; font-size: 18px; line-height: 1;
    display: grid; place-items: center; cursor: pointer; padding: 0;
    transition: background 0.1s, border-color 0.1s; box-shadow: none;
  }
  .nav-btn:hover:not(:disabled) { background: rgba(255,255,255,0.18); border-color: rgba(255,255,255,0.6); }
  .nav-btn:disabled { opacity: 0.3; cursor: default; }
  .nav-count { font-family: var(--font-mono); font-size: 12px; color: #aaa; min-width: 36px; text-align: center; }
</style>
