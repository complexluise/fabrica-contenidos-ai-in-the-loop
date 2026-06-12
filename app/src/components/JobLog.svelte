<script>
  // [D-081] El registro en vivo de un job (x2 copias menos).
  let { log = [], placeholder = "El progreso aparece aca mientras la maquina trabaja…" } = $props();
  let open = $state(true);
</script>

<div class="log-wrap">
  <button class="log-toggle eyebrow" onclick={() => (open = !open)}>
    {open ? "▾" : "▸"} Registro en vivo
  </button>
  {#if open}
    <div class="log mono">
      {#if log.length === 0}
        <span class="muted">{placeholder}</span>
      {:else}
        {#each log as l}<div>{l}</div>{/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .log-wrap { margin-top: 22px; }
  .log-toggle { background: transparent; border: none; padding: 4px 0; cursor: pointer; box-shadow: none; }
  .log-toggle:hover { color: var(--ink); box-shadow: none; }
  .log {
    margin-top: 8px; background: #211c16; color: #d8cdb8; border: 1px solid var(--line-2);
    border-radius: var(--r); padding: 14px 16px; min-height: 130px; max-height: 420px;
    overflow: auto; font-size: 12.5px; line-height: 1.65; white-space: pre-wrap;
  }
</style>
