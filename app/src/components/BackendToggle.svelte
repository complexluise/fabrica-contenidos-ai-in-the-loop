<script>
  // [D-081] Toggle del motor de imagen fal/google (D-051/D-053). x2 copias menos.
  let { value = $bindable("fal"), hasGoogle = false, disabled = false } = $props();
</script>

<div class="backend-toggle" title="Motor de imagen (D-051/D-053)">
  <span class="bt-lbl">motor</span>
  <button class="bt-opt" class:active={value === "fal"} {disabled}
          onclick={() => (value = "fal")}>fal</button>
  <button class="bt-opt" class:active={value === "google"} disabled={disabled || !hasGoogle}
          onclick={() => (value = "google")}
          title={hasGoogle ? "Gemini imagen (sin fal)" : "Falta GOOGLE_API_KEY"}>Google</button>
</div>

<style>
  .backend-toggle { display: inline-flex; align-items: center; gap: 0; border: 1.5px solid var(--line-2); border-radius: 999px; overflow: hidden; }
  .bt-lbl { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); padding: 0 8px 0 11px; }
  .bt-opt { border: none; border-radius: 0; box-shadow: none; background: var(--paper); padding: 6px 12px; font-size: 13px; font-weight: 600; color: var(--ink-soft); }
  .bt-opt.active { background: var(--blue); color: #fff; }
  .bt-opt:disabled { opacity: 0.4; }
</style>
