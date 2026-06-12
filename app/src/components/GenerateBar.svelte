<script>
  // [D-081] El header de generacion ("La IA propone" + costo SIEMPRE visible
  // antes del boton que gasta, D-052/D-061). x3 copias menos. El contenido
  // variable entra por snippets: `info` (texto+costo) y `controls` (knobs+CTA).
  let { info, controls } = $props();
</script>

<div class="generate card">
  <div class="gen-l">
    <div class="eyebrow" style="color:var(--blue-deep)">La IA propone</div>
    {@render info()}
  </div>
  <div class="gen-controls">
    {@render controls()}
  </div>
</div>

<style>
  .generate { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; padding: 16px 20px; margin-bottom: 14px; }
  .gen-l { flex: 1; min-width: 220px; }
  .gen-l :global(.gen-help) { font-size: 13px; margin: 4px 0 0; max-width: 52ch; color: var(--ink-soft); }
  .gen-l :global(.est-line) { font-size: 12.5px; margin: 6px 0 0; }
  .gen-l :global(.est-line b) { color: var(--ink); font-family: var(--font-mono); }
  .gen-controls { display: flex; align-items: center; gap: 9px; }
  .gen-controls :global(.n-lbl) { display: flex; flex-direction: column; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); gap: 3px; }
  .gen-controls :global(.n-lbl input) { width: 64px; font-family: var(--font-mono); }
  .gen-controls :global(.n-lbl select) { font-size: 13px; }
</style>
