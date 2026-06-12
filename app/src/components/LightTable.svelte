<script>
  // [D-081] La mesa de luz: candidatos -> el humano elige (AI-in-the-Loop).
  // Estaba implementada DOS veces (Casting y Encuadres); ahora es una. El
  // descarte y los badges de origen son opcionales (Encuadres los usa).
  let { urls = [], picked = null, sources = null, disabled = false,
        onpick, ondiscard } = $props();
</script>

<div class="lighttable">
  {#each urls as url, i}
    <div class="cell-wrap">
      <button class="cell" class:sel={picked === i} {disabled}
              onclick={() => onpick?.(i)}>
        <img src={url} alt="candidato {i}" loading="lazy" />
        <span class="idx">{i}</span>
        {#if sources?.[i] === "upload"}
          <span class="src-badge" title="La subiste vos; no la generó la IA">tu foto</span>
        {/if}
        {#if picked === i}<span class="stamp">elegido</span>{/if}
      </button>
      {#if ondiscard}
        <button class="discard" title="Descartar este candidato" {disabled}
                onclick={() => ondiscard(i)}>✕</button>
      {/if}
    </div>
  {/each}
</div>

<style>
  .lighttable { display: flex; flex-wrap: wrap; gap: 12px; background: #2a251e; border: 1px solid var(--line-2); border-radius: var(--r); padding: 14px; box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35); }
  .cell { position: relative; padding: 0; background: #1a1611; border: 2px solid transparent; border-radius: var(--r-sm); overflow: hidden; line-height: 0; box-shadow: none; transition: transform 0.1s ease, border-color 0.12s ease; }
  .cell:hover { transform: translateY(-3px) scale(1.01); border-color: rgba(255, 255, 255, 0.4); box-shadow: 0 8px 20px -6px rgba(0,0,0,0.6); }
  .cell img { display: block; max-width: 210px; max-height: 230px; }
  .cell.sel { border-color: var(--red); box-shadow: 0 0 0 3px var(--red-wash), 0 8px 22px -6px rgba(0,0,0,0.6); }
  .idx { position: absolute; top: 7px; left: 7px; background: rgba(0,0,0,0.62); color: #fff; border-radius: var(--r-sm); padding: 0 7px; font-family: var(--font-mono); font-size: 12px; }
  .stamp { position: absolute; top: 9px; right: -28px; transform: rotate(14deg); background: var(--red); color: #fff8f2; font-weight: 700; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 30px; box-shadow: 0 2px 6px rgba(0,0,0,0.4); }
  .src-badge { position: absolute; bottom: 7px; left: 7px; z-index: 1; background: var(--blue-deep); color: #fff; font-size: 10px; font-weight: 700; letter-spacing: 0.04em; border-radius: var(--r-sm); padding: 1px 7px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); }
  .cell-wrap { position: relative; line-height: 0; }
  .cell-wrap .cell { display: block; }
  .discard { position: absolute; top: 5px; right: 5px; z-index: 2; width: 22px; height: 22px; padding: 0; line-height: 1; border-radius: 50%; border: none; box-shadow: 0 1px 4px rgba(0,0,0,0.5); background: rgba(0,0,0,0.55); color: #fff; font-size: 12px; cursor: pointer; opacity: 0; transition: opacity 0.12s ease; }
  .cell-wrap:hover .discard { opacity: 1; }
  .discard:hover { background: var(--red); }
  .discard:disabled { opacity: 0; }
</style>
