<script>
  // [D-081] Barra pegajosa de confirmacion al pie (3 copias menos).
  let { children } = $props();
</script>

<div class="savebar">
  {@render children()}
</div>

<style>
  .savebar { position: sticky; bottom: 0; margin-top: 26px; padding: 16px 0 8px; background: linear-gradient(0deg, var(--paper) 60%, transparent); display: flex; align-items: center; gap: 14px; }
  .savebar :global(.saved-seal) { font-size: 13px; font-weight: 700; color: var(--ok); background: var(--ok-wash); border-radius: 999px; padding: 6px 14px; }
  .savebar :global(.muted) { color: var(--ink-soft); }
</style>
