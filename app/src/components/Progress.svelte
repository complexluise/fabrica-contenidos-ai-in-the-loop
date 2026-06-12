<script>
  // [D-081] Spinner + ultima linea del job (3 copias menos).
  let { text = "", small = false } = $props();
</script>

<div class="progress mono" class:small>
  <span class="spin" class:sm={small}></span>{text}
</div>

<style>
  .progress { display: flex; align-items: center; gap: 10px; background: var(--blue-wash); border: 1px solid #b9c2ee; color: var(--blue-deep); border-radius: var(--r); padding: 10px 14px; font-size: 13px; }
  .progress.small { background: transparent; border: none; padding: 0; font-size: 12px; margin-bottom: 8px; }
  .spin { width: 13px; height: 13px; border: 2px solid var(--blue-deep); border-right-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
  .spin.sm { width: 11px; height: 11px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
