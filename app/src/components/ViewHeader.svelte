<script>
  // [D-081] Encabezado de vista: eyebrow + titulo + lede. El lede entra como
  // children (snippet de Svelte 5) para conservar el markup rico de cada vista.
  let { eyebrow, title, children } = $props();
</script>

<header class="head">
  <div class="eyebrow">{eyebrow}</div>
  <h1>{title}</h1>
  {#if children}
    <p class="lede">{@render children()}</p>
  {/if}
</header>

<style>
  .head { margin-bottom: 18px; }
  .head h1 { margin: 5px 0 8px; }
  .lede { max-width: 58ch; color: var(--ink-2); font-size: 16px; }
  .lede :global(.b) { color: var(--blue-deep); }
  .lede :global(.r) { color: var(--red-deep); }
  .lede :global(span[title]) { border-bottom: 1.5px dotted var(--ink-soft); cursor: help; }
</style>
