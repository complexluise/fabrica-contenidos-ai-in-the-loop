<script>
  // [D-081] La tira de advertencia con accion opcional (4 copias menos).
  let { actionLabel = "", onaction, children } = $props();
</script>

<div class="warn-strip">
  <span class="body">{@render children()}</span>
  {#if actionLabel}
    <button class="small" onclick={onaction}>{actionLabel}</button>
  {/if}
</div>

<style>
  .warn-strip {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--warn-wash); border: 1.5px solid #e0c089; color: #6b4a12;
    border-radius: var(--r); padding: 12px 16px; margin-bottom: 18px;
  }
  .warn-strip button { margin-left: auto; }
  .body { display: contents; }
</style>
