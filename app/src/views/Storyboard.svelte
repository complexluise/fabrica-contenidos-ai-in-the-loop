<script>
  import { get, put, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let doc = $state(null); // { title, brief, scenes:[{id,beat,prompt,characters,shots:[...]}] }
  let error = $state("");
  let msg = $state("");
  let dirty = $state(false);
  let saving = $state(false);

  $effect(() => {
    if (!slug) return;
    doc = null; error = ""; msg = ""; dirty = false;
    get(`/api/projects/${slug}`)
      .then((d) => {
        doc = {
          title: d.title || "",
          brief: d.brief || "",
          scenes: d.scenes.map((s) => ({
            id: s.id,
            beat: s.beat || "",
            prompt: s.prompt || "",
            characters: s.characters || [],
            shots: (s.shots || []).map((sh) => ({
              framing: sh.framing || "",
              duration_s: sh.duration_s ?? 3,
              voiceover: sh.voiceover || "",
              caption: sh.caption || "",
            })),
          })),
        };
      })
      .catch((e) => (error = humanError(e)));
  });

  const touch = () => { dirty = true; msg = ""; };
  const sceneDur = (s) => s.shots.reduce((a, sh) => a + (Number(sh.duration_s) || 0), 0);
  const total = $derived(doc ? doc.scenes.reduce((a, s) => a + sceneDur(s), 0) : 0);

  function uniqueId() {
    const used = new Set(doc.scenes.map((s) => s.id));
    let n = doc.scenes.length + 1;
    while (used.has(`s${n}`)) n++;
    return `s${n}`;
  }

  function addScene() {
    doc.scenes = [...doc.scenes, {
      id: uniqueId(), beat: "", prompt: "", characters: [],
      shots: [{ framing: "", duration_s: 3, voiceover: "", caption: "" }],
    }];
    touch();
  }
  function deleteScene(i) {
    if (!confirm(`¿Eliminar la escena "${doc.scenes[i].id}"?`)) return;
    doc.scenes = doc.scenes.filter((_, k) => k !== i);
    touch();
  }
  function move(i, d) {
    const j = i + d;
    if (j < 0 || j >= doc.scenes.length) return;
    const a = [...doc.scenes];
    [a[i], a[j]] = [a[j], a[i]];
    doc.scenes = a;
    touch();
  }
  function addShot(s) {
    s.shots = [...s.shots, { framing: "", duration_s: 3, voiceover: "", caption: "" }];
    touch();
  }
  function deleteShot(s, j) {
    if (s.shots.length === 1) return; // siempre al menos un plano
    s.shots = s.shots.filter((_, k) => k !== j);
    touch();
  }

  async function save(sign) {
    error = ""; msg = ""; saving = true;
    const body = {
      sign: !!sign,
      title: doc.title,
      brief: doc.brief,
      scenes: doc.scenes.map((s) => ({
        id: s.id,
        beat: s.beat || null,
        prompt: s.prompt,
        shots: s.shots.map((sh) => ({
          framing: sh.framing || "",
          duration_s: Number(sh.duration_s) || 1,
          voiceover: sh.voiceover || null,
          caption: sh.caption || null,
        })),
      })),
    };
    try {
      const r = await put(`/api/projects/${slug}`, body);
      dirty = false;
      const dropped = r.dropped_selections?.length
        ? ` (se limpiaron selecciones huérfanas: ${r.dropped_selections.join(", ")})` : "";
      msg = (sign ? "Plan firmado." : "Borrador guardado.") + dropped;
      await refreshStatus();
    } catch (e) {
      error = humanError(e);
    } finally {
      saving = false;
    }
  }

  let signed = $derived(studio.status?.storyboard?.signed);
</script>

{#if error && !doc}
  <p class="error">{error}</p>
{:else if doc}
  <header class="head">
    <div class="eyebrow">Paso 2 · vos decidís</div>
    <input class="title-in" bind:value={doc.title} oninput={touch} placeholder="Título del proyecto" />
    <p class="lede muted">Editá el plan: escenas y planos. La IA propuso; vos firmás.</p>
    <div class="meta">
      <span class="pill">~{total.toFixed(0)}s</span>
      <span class="pill">{doc.scenes.length} escena{doc.scenes.length === 1 ? "" : "s"}</span>
      {#if signed && !dirty}<span class="pill ok">✓ firmado</span>
      {:else if dirty}<span class="pill warn">cambios sin firmar</span>{/if}
    </div>
  </header>

  <section class="card pad">
    <span class="lbl">Sinopsis</span>
    <textarea class="brief-in" bind:value={doc.brief} oninput={touch} rows="2"
              placeholder="Una o dos frases sobre el proyecto"></textarea>
  </section>

  <div class="toolbar">
    <h2>Escenas</h2>
    <span class="spacer"></span>
    <button class="small ghost" onclick={addScene}>+ Agregar escena</button>
  </div>

  {#each doc.scenes as s, i (s.id)}
    <section class="scene">
      <div class="shead">
        <span class="sid mono">{s.id}</span>
        <input class="beat-in" bind:value={s.beat} oninput={touch} placeholder="beat (etiqueta)" />
        {#if s.characters.length}<span class="who">{s.characters.join(", ")}</span>{/if}
        <span class="dur mono">{sceneDur(s).toFixed(0)}s</span>
        <span class="spacer"></span>
        <button class="icon" title="Subir" onclick={() => move(i, -1)} disabled={i === 0}>↑</button>
        <button class="icon" title="Bajar" onclick={() => move(i, 1)} disabled={i === doc.scenes.length - 1}>↓</button>
        <button class="icon danger" title="Eliminar" onclick={() => deleteScene(i)}>✕</button>
      </div>

      <div class="sbody">
        <span class="lbl">Qué pasa (visual del beat)</span>
        <textarea class="prompt-in" bind:value={s.prompt} oninput={touch} rows="2"
                  placeholder="setting + personajes (sin diálogo)"></textarea>

        <div class="shots">
          {#each s.shots as sh, j}
            <div class="shot">
              <div class="shot-h">
                <span class="ptag">Plano {j + 1}</span>
                <input class="fr-in" bind:value={sh.framing} oninput={touch} placeholder="encuadre / acción" />
                <input class="num-in" type="number" min="1" step="1" bind:value={sh.duration_s} oninput={touch} />
                <span class="muted s">s</span>
                <button class="icon danger" title="Quitar plano" onclick={() => deleteShot(s, j)}
                        disabled={s.shots.length === 1}>✕</button>
              </div>
              <div class="shot-fields">
                <input class="vo-in" bind:value={sh.voiceover} oninput={touch} placeholder="🎙 voz en off (opcional)" />
                <input class="cap-in" bind:value={sh.caption} oninput={touch} placeholder="▭ caption en pantalla (opcional)" />
              </div>
            </div>
          {/each}
          <button class="small ghost addshot" onclick={() => addShot(s)}>+ plano</button>
        </div>
      </div>
    </section>
  {/each}

  <div class="savebar" class:dirty class:signed={signed && !dirty}>
    <button class="primary sign" onclick={() => save(true)} disabled={saving}>
      {saving ? "Firmando…" : signed && !dirty ? "Plan firmado ✓ — volver a firmar" : "Firmar el plan"}
    </button>
    <button class="ghost small" onclick={() => save(false)} disabled={saving || !dirty}>
      Guardar borrador
    </button>
    {#if msg}<span class="ok-msg">✓ {msg}</span>{/if}
    {#if error}<span class="error inline">{error}</span>{/if}
    <span class="spacer"></span>
    {#if signed && !dirty}
      <button class="ghost" onclick={() => goTo("elegir")}>Siguiente: Elegir →</button>
    {/if}
  </div>
{:else}
  <p class="muted">Cargando…</p>
{/if}

<style>
  .head { margin-bottom: 14px; }
  .title-in {
    font-family: var(--font-display); font-size: 30px; font-weight: 600; letter-spacing: -0.02em;
    width: 100%; border: none; border-bottom: 2px solid transparent; padding: 2px 0; background: transparent;
  }
  .title-in:hover { border-bottom-color: var(--line); }
  .title-in:focus { border-bottom-color: var(--red); outline: none; box-shadow: none; }
  .lede { font-size: 15px; margin: 6px 0 10px; }
  .meta { display: flex; gap: 7px; }

  .card.pad { padding: 12px 16px; margin: 12px 0; }
  .lbl { display: block; font-size: 11px; font-weight: 700; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px; }
  /* nivel editorial: inset dentro de card, no compiten con el contorno del card */
  .brief-in, .prompt-in {
    width: 100%; resize: vertical; font-size: 14.5px; line-height: 1.6;
    background: var(--paper-2); border-color: var(--line);
  }

  .toolbar { display: flex; align-items: center; gap: 8px; margin: 24px 0 10px; }
  .toolbar h2 { margin: 0; }
  .spacer { flex: 1; }

  .scene { background: var(--card); border: 1.5px solid var(--line); border-radius: var(--r); margin: 9px 0; overflow: hidden; }
  .shead { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--paper-2); border-bottom: 1px solid var(--line); }
  .sid { font-weight: 700; color: var(--blue-deep); flex-shrink: 0; }
  /* beat: campo inline en cabecera, se funde con el fondo paper-2 del shead */
  .beat-in {
    max-width: 220px; font-size: 13px; padding: 3px 8px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .beat-in:focus { background: var(--card); }
  .who { color: var(--ink-soft); font-size: 12px; }
  .dur { color: var(--ink-soft); font-size: 12px; }

  .icon {
    width: 28px; height: 28px; padding: 0; display: grid; place-items: center;
    background: var(--paper); border: 1px solid var(--line-2); border-radius: var(--r-sm);
    font-size: 14px; color: var(--ink-soft); box-shadow: none;
  }
  .icon:hover:not(:disabled) { background: var(--card); color: var(--ink); }
  .icon:disabled { opacity: 0.35; }
  .icon.danger:hover:not(:disabled) { background: var(--red-wash); color: var(--red-deep); border-color: var(--red); }

  .sbody { padding: 12px 16px 14px; }
  .shots { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
  .shot { border: 1px dashed var(--line-2); border-radius: var(--r-sm); padding: 9px 11px; }
  .shot-h { display: flex; align-items: center; gap: 8px; }
  .ptag { background: var(--blue); color: #fff; border-radius: var(--r-sm); padding: 1px 9px; font-size: 12px; font-weight: 700; flex-shrink: 0; }
  /* campos de plano: subdued, se funden con el contenedor de plano (no compiten con el dashed card) */
  .fr-in {
    flex: 1; font-size: 13.5px; padding: 4px 8px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .fr-in:focus { background: var(--card); }
  .num-in {
    width: 56px; text-align: right; font-family: var(--font-mono); padding: 4px 6px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .num-in:focus { background: var(--card); }
  .s { font-size: 12px; }
  .shot-fields { display: flex; gap: 8px; margin-top: 7px; }
  .vo-in, .cap-in {
    flex: 1; font-size: 13px; padding: 4px 8px;
    background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm);
  }
  .addshot { align-self: flex-start; }

  .savebar {
    position: sticky; bottom: 0; margin: 22px -48px -80px; padding: 16px 48px;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    background: var(--paper); border-top: 1.5px solid var(--line-2);
  }
  .savebar.dirty { border-top-color: var(--red); }
  .savebar.signed { border-top-color: var(--ok); }
  .savebar .sign { background: var(--red); }
  .savebar.signed .sign { background: var(--ok); }
  .pill.ok { background: var(--ok); color: #fff; }
  .pill.warn { background: var(--warn, #e0a800); color: #fff; }
  .ok-msg { color: var(--ok); font-weight: 600; font-size: 13px; }
  .error.inline { margin: 0; font-size: 13px; }
  .muted { color: var(--ink-soft); }
</style>
