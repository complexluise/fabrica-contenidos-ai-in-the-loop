<script>
  // [D-081] El nodo del bucle (circulo numerado / tick / icono por actor).
  // Estaba duplicado entre la espina del sidebar (App) y las estaciones del
  // Inicio — el mismo lenguaje visual, una sola implementacion.
  let { n = "", actor = "lee", done = false, size = 30, icon = "" } = $props();
</script>

<span class="stage-node actor-{actor}" class:done style="--sz:{size}px">
  {#if done}
    <svg viewBox="0 0 16 16" class="ico"><path d="M3 8.5l3.2 3L13 4.5" fill="none"
      stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
  {:else if icon === "home"}
    <svg viewBox="0 0 16 16" class="ico"><path d="M2.5 7.5L8 3l5.5 4.5V13a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1z"
      fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
  {:else}
    {n}
  {/if}
</span>

<style>
  .stage-node {
    position: relative; z-index: 1; width: var(--sz); height: var(--sz); flex-shrink: 0;
    display: grid; place-items: center; border-radius: 50%;
    border: 2px solid var(--line-2); background: var(--paper);
    font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--ink-soft);
  }
  .ico { width: 16px; height: 16px; }
  .actor-tu { border-color: var(--red); color: var(--red-deep); }
  .actor-ia { border-color: var(--blue); color: var(--blue-deep); }
  .done { background: var(--ok); border-color: var(--ok); color: #fff; }
</style>
