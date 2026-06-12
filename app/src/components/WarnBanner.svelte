<script>
  // [D-081] Banner de integridad/avisos: broken (rojo) | advisory (ambar).
  let { kind = "advisory", children } = $props();
</script>

<div class="warn-banner {kind}">
  {@render children()}
</div>

<style>
  .warn-banner { border-radius: var(--r); padding: 10px 14px; margin-bottom: 12px; font-size: 13.5px; display: flex; flex-direction: column; gap: 4px; }
  .warn-banner.broken { background: var(--red-wash); border: 1px solid var(--red); color: var(--red-deep); }
  .warn-banner.advisory { background: var(--warn-wash, #fbeed0); border: 1px solid var(--warn, #e0a93b); color: var(--warn-deep, #7a5400); }
  .warn-banner :global(.mono) { font-family: var(--font-mono); }
  .warn-banner :global(ul) { margin: 2px 0 0; padding-left: 18px; }
  .warn-banner :global(li) { margin: 1px 0; }
</style>
