<script>
  import { get, put, humanError } from "../lib/api.js";
  import { studio, goTo, refreshStatus } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let doc   = $state(null);
  let cand  = $state({ keyframes: {}, cast: {}, selections: {} });
  let editing = $state({});     // { [sceneId]: true } tarjetas en modo edicion
  let expandedAudio = $state({}); // { "sceneId_shotIdx": true } audio por plano
  let error = $state("");
  let msg   = $state("");
  let dirty = $state(false);
  let saving = $state(false);

  $effect(() => {
    if (!slug) return;
    doc = null; error = ""; msg = ""; dirty = false;
    cand = { keyframes: {}, cast: {}, selections: {} };
    editing = {};

    get(`/api/projects/${slug}`)
      .then((d) => {
        doc = {
          title: d.title || "",
          brief: d.brief || "",
          scenes: d.scenes.map((s) => ({
            id: s.id, beat: s.beat || "", prompt: s.prompt || "",
            dialogue: s.dialogue || "", ambience: s.ambience || "",
            characters: s.characters || [],
            shots: (s.shots || []).map((sh) => ({
              framing: sh.framing || "", duration_s: sh.duration_s ?? 3,
              voiceover: sh.voiceover || "", caption: sh.caption || "",
              sfx: sh.sfx || "",
            })),
          })),
        };
      })
      .catch((e) => (error = humanError(e)));

    // Cargar candidatos + selecciones para los thumbnails (best-effort)
    get(`/api/projects/${slug}/candidates`)
      .then((c) => { cand = c; })
      .catch(() => {});
  });

  const touch = () => { dirty = true; msg = ""; };
  const sceneDur = (s) => s.shots.reduce((a, sh) => a + (Number(sh.duration_s) || 0), 0);
  const total = $derived(doc ? doc.scenes.reduce((a, s) => a + sceneDur(s), 0) : 0);

  // Devuelve la URL del keyframe elegido para una escena, o null
  function selectedKf(sceneId) {
    const idx = cand.selections?.[sceneId];
    if (idx == null) return null;
    return cand.keyframes?.[sceneId]?.[idx] ?? null;
  }
  const hasKfCands = (sceneId) => (cand.keyframes?.[sceneId]?.length ?? 0) > 0;

  const hasAudio = (sh) => !!(sh.voiceover || sh.caption || sh.sfx);
  function toggleAudio(sceneId, j) {
    const k = `${sceneId}_${j}`;
    expandedAudio = { ...expandedAudio, [k]: !expandedAudio[k] };
  }

  function toggleEdit(id) {
    if (editing[id]) {
      // Colapsando: si hay cambios sin guardar, guardar ahora (fire-and-forget)
      if (dirty) save(false);
      else editing = { ...editing, [id]: false };
    } else {
      editing = { ...editing, [id]: true };
    }
  }

  function uniqueId() {
    const used = new Set(doc.scenes.map((s) => s.id));
    let n = doc.scenes.length + 1;
    while (used.has(`s${n}`)) n++;
    return `s${n}`;
  }

  function addScene() {
    const id = uniqueId();
    doc.scenes = [...doc.scenes, {
      id, beat: "", prompt: "", dialogue: "", ambience: "", characters: [],
      shots: [{ framing: "", duration_s: 3, voiceover: "", caption: "", sfx: "" }],
    }];
    editing = { ...editing, [id]: true }; // nueva escena abre en modo edicion
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
    doc.scenes = a; touch();
  }
  function addShot(s) {
    s.shots = [...s.shots, { framing: "", duration_s: 3, voiceover: "", caption: "", sfx: "" }];
    touch();
  }
  function deleteShot(s, j) {
    if (s.shots.length === 1) return;
    s.shots = s.shots.filter((_, k) => k !== j);
    touch();
  }

  async function save(sign) {
    error = ""; msg = ""; saving = true;
    const body = {
      sign: !!sign, title: doc.title, brief: doc.brief,
      scenes: doc.scenes.map((s) => ({
        id: s.id, beat: s.beat || null, prompt: s.prompt,
        dialogue: s.dialogue || null, ambience: s.ambience || null,
        shots: s.shots.map((sh) => ({
          framing: sh.framing || "", duration_s: Number(sh.duration_s) || 1,
          voiceover: sh.voiceover || null, caption: sh.caption || null,
          sfx: sh.sfx || null,
        })),
      })),
    };
    try {
      const r = await put(`/api/projects/${slug}`, body);
      dirty = false;
      editing = {};
      expandedAudio = {};
      const dropped = r.dropped_selections?.length
        ? ` (selecciones limpiadas: ${r.dropped_selections.join(", ")})` : "";
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
    <p class="lede muted">El storyboard es el centro. La IA propuso; vos lo firmás y de acá se genera todo.</p>
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
    {@const isEditing = !!editing[s.id]}
    {@const kfUrl = selectedKf(s.id)}
    {@const hasCands = hasKfCands(s.id)}

    <section class="scene" class:is-editing={isEditing}>

      <!-- Cabecera: siempre visible -->
      <div class="shead">
        <span class="sid mono">{s.id}</span>
        {#if isEditing}
          <input class="beat-in" bind:value={s.beat} oninput={touch} placeholder="beat / título de la escena" />
        {:else if s.beat}
          <span class="beat-label">{s.beat}</span>
        {/if}
        {#if s.characters.length && !isEditing}
          <span class="who">{s.characters.join(", ")}</span>
        {/if}
        <span class="dur mono">{sceneDur(s).toFixed(0)}s</span>
        <span class="spacer"></span>
        <button class="icon" title="Subir" onclick={() => move(i, -1)} disabled={i === 0}>↑</button>
        <button class="icon" title="Bajar" onclick={() => move(i, 1)} disabled={i === doc.scenes.length - 1}>↓</button>
        <button class="icon danger" title="Eliminar escena" onclick={() => deleteScene(i)}>✕</button>
        <button class="small {isEditing ? 'primary' : 'ghost'} edit-btn" onclick={() => toggleEdit(s.id)}>
          {isEditing ? (dirty ? "Guardar" : "Listo") : "Editar"}
        </button>
      </div>

      {#if isEditing}
        <!-- MODO EDICIÓN: L1 visual → L2 audio escena → L3 planos -->
        <div class="sbody">

          <!-- L1: Lo que la cámara ve -->
          <span class="lbl">Qué pasa — visual del beat</span>
          <textarea class="prompt-in" bind:value={s.prompt} oninput={touch} rows="3"
                    placeholder="setting + personajes + acción física. Lo que la cámara VE. Sin diálogo."></textarea>

          <!-- L2: Audio de escena — secundario, agrupado en franja discreta -->
          <div class="scene-audio">
            <div class="audio-col">
              <span class="audio-lbl">Diálogo</span>
              <textarea class="audio-ta" bind:value={s.dialogue} oninput={touch} rows="2"
                        placeholder="'Personaje: frase exacta.' — vacío si no hay diálogo"></textarea>
            </div>
            <div class="audio-col">
              <span class="audio-lbl">Ambience</span>
              <textarea class="audio-ta" bind:value={s.ambience} oninput={touch} rows="2"
                        placeholder="room tone: 'lluvia sobre asfalto, tráfico lejano'"></textarea>
            </div>
          </div>

          <!-- L3: Planos — sub-elementos anidados -->
          <div class="shots">
            {#each s.shots as sh, j}
              {@const ak = `${s.id}_${j}`}
              {@const audioOpen = !!expandedAudio[ak] || hasAudio(sh)}
              <div class="shot">
                <div class="shot-h">
                  <span class="ptag">P{j + 1}</span>
                  <input class="fr-in" bind:value={sh.framing} oninput={touch} placeholder="encuadre / acción" />
                  <input class="num-in" type="number" min="1" step="1" bind:value={sh.duration_s} oninput={touch} />
                  <span class="muted s">s</span>
                  <button class="audio-tog" class:open={audioOpen}
                          onclick={() => toggleAudio(s.id, j)}
                          title={audioOpen ? "Cerrar audio" : "Agregar vo / caption / sfx"}>
                    {hasAudio(sh) ? "♪" : "~"}
                  </button>
                  <button class="icon danger" title="Quitar plano" onclick={() => deleteShot(s, j)}
                          disabled={s.shots.length === 1}>✕</button>
                </div>
                {#if audioOpen}
                  <div class="shot-audio">
                    <input class="audio-in" bind:value={sh.voiceover} oninput={touch} placeholder="voz en off" />
                    <input class="audio-in" bind:value={sh.caption} oninput={touch} placeholder="caption en pantalla" />
                    <input class="audio-in" bind:value={sh.sfx} oninput={touch} placeholder="sfx de la acción" />
                  </div>
                {/if}
              </div>
            {/each}
            <button class="small ghost addshot" onclick={() => addShot(s)}>+ plano</button>
          </div>
        </div>

      {:else}
        <!-- MODO LECTURA: documento visual con thumbnail del keyframe -->
        <div class="read-body">
          <div class="read-text">
            {#if s.beat}
              <p class="beat-display">{s.beat}</p>
            {/if}
            <p class="prompt-display">{s.prompt || "—"}</p>
            {#if s.dialogue}
              <p class="dialogue-display">{s.dialogue}</p>
            {/if}
            {#if s.ambience}
              <p class="ambience-display">~ {s.ambience}</p>
            {/if}
            <div class="shots-chips">
              {#each s.shots as sh, j}
                <span class="chip">
                  <span class="chip-n">P{j + 1}</span>
                  <span class="chip-fr">{sh.framing || "—"}</span>
                  <span class="chip-dur">{sh.duration_s}s</span>
                </span>
              {/each}
            </div>
          </div>

          <div class="kf-col">
            {#if kfUrl}
              <img class="kf-thumb" src={kfUrl} alt="keyframe {s.id}" />
              <button class="small ghost kf-btn" onclick={() => goTo("elegir")}>Cambiar →</button>
            {:else if hasCands}
              <div class="kf-placeholder pending">
                <span class="kf-icon">◈</span>
                <span class="muted kf-hint">candidatos listos</span>
                <button class="small machine kf-btn" onclick={() => goTo("elegir")}>Elegir →</button>
              </div>
            {:else}
              <div class="kf-placeholder empty">
                <span class="kf-icon muted">◇</span>
                <span class="muted kf-hint">sin keyframe</span>
                <button class="small ghost kf-btn" onclick={() => goTo("elegir")}>Generar →</button>
              </div>
            {/if}
          </div>
        </div>
      {/if}

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
  /* --- cabecera del documento --- */
  .head { margin-bottom: 14px; }
  .title-in {
    font-family: var(--font-display); font-size: 30px; font-weight: 600;
    letter-spacing: -0.02em; width: 100%; border: none;
    border-bottom: 2px solid transparent; padding: 2px 0; background: transparent;
  }
  .title-in:hover { border-bottom-color: var(--line); }
  .title-in:focus { border-bottom-color: var(--red); outline: none; box-shadow: none; }
  .lede { font-size: 15px; margin: 6px 0 10px; }
  .meta { display: flex; gap: 7px; }

  .card.pad { padding: 12px 16px; margin: 12px 0; }
  .lbl {
    display: block; font-size: 11px; font-weight: 700; color: var(--ink-soft);
    text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px;
  }
  .brief-in {
    width: 100%; resize: vertical; font-size: 14.5px; line-height: 1.6;
    background: var(--paper-2); border-color: var(--line);
  }
  .prompt-in {
    width: 100%; resize: vertical; font-size: 14.5px; line-height: 1.65;
    background: var(--paper-2); border-color: var(--line);
  }

  .toolbar { display: flex; align-items: center; gap: 8px; margin: 24px 0 10px; }
  .toolbar h2 { margin: 0; }
  .spacer { flex: 1; }

  /* --- tarjeta de escena --- */
  .scene {
    background: var(--card); border: 1.5px solid var(--line);
    border-radius: var(--r); margin: 9px 0; overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .scene:hover { box-shadow: var(--shadow); }
  .scene.is-editing { border-color: var(--red); box-shadow: 0 0 0 3px var(--red-wash); }

  /* Cabecera de escena */
  .shead {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    background: var(--paper-2); border-bottom: 1px solid var(--line);
  }
  .sid { font-family: var(--font-mono); font-weight: 700; color: var(--blue-deep); flex-shrink: 0; font-size: 13px; }
  .beat-label {
    font-family: var(--font-display); font-weight: 600; font-size: 15px;
    letter-spacing: -0.01em; color: var(--ink);
  }
  .who { color: var(--ink-soft); font-size: 12px; }
  .dur { font-family: var(--font-mono); color: var(--ink-soft); font-size: 12px; }
  .edit-btn { flex-shrink: 0; }

  /* Iconos de accion */
  .icon {
    width: 28px; height: 28px; padding: 0; display: grid; place-items: center;
    background: var(--paper); border: 1px solid var(--line-2); border-radius: var(--r-sm);
    font-size: 14px; color: var(--ink-soft); box-shadow: none;
  }
  .icon:hover:not(:disabled) { background: var(--card); color: var(--ink); }
  .icon:disabled { opacity: 0.35; }
  .icon.danger:hover:not(:disabled) { background: var(--red-wash); color: var(--red-deep); border-color: var(--red); }

  /* --- MODO LECTURA --- */
  .read-body {
    display: grid;
    grid-template-columns: 1fr 200px;
  }
  .read-text {
    padding: 16px 18px; display: flex; flex-direction: column; gap: 10px;
    border-right: 1px solid var(--line);
  }
  .beat-display {
    font-family: var(--font-display); font-size: 20px; font-weight: 600;
    letter-spacing: -0.02em; line-height: 1.15; color: var(--ink); margin: 0;
  }
  .prompt-display {
    font-size: 13.5px; line-height: 1.7; color: var(--ink-2); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
  }
  .dialogue-display {
    font-style: italic; font-size: 13px; color: var(--ink-2); margin: 0;
    border-left: 2.5px solid var(--line-2); padding-left: 10px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .ambience-display {
    font-size: 12px; color: var(--ink-soft); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
  }
  .shots-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 2px; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--paper-2); border: 1px solid var(--line);
    border-radius: 999px; padding: 2px 10px; font-size: 11.5px; color: var(--ink-2);
  }
  .chip-n { font-family: var(--font-mono); font-weight: 700; color: var(--blue-deep); font-size: 11px; }
  .chip-fr { color: var(--ink-2); }
  .chip-dur { font-family: var(--font-mono); color: var(--ink-soft); font-size: 11px; }

  /* Columna del keyframe */
  .kf-col {
    background: var(--paper-2); padding: 14px 12px;
    display: flex; flex-direction: column; align-items: center;
    gap: 8px; justify-content: center;
  }
  .kf-thumb {
    width: 100%; border-radius: var(--r-sm);
    border: 1px solid var(--line-2); object-fit: cover;
    aspect-ratio: 16 / 9; display: block;
  }
  .kf-placeholder {
    width: 100%; aspect-ratio: 16 / 9; border-radius: var(--r-sm);
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 6px;
  }
  .kf-placeholder.empty { border: 1.5px dashed var(--line-2); background: var(--paper); }
  .kf-placeholder.pending { border: 1.5px dashed var(--blue); background: var(--blue-wash); }
  .kf-icon { font-size: 22px; line-height: 1; }
  .kf-hint { font-size: 11px; }
  .kf-btn { font-size: 11.5px; padding: 3px 10px; }

  /* --- MODO EDICIÓN --- */
  .sbody { padding: 14px 16px 18px; display: flex; flex-direction: column; gap: 10px; }

  /* L2 — Audio de escena (secundario, agrupado) */
  .scene-audio {
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
    background: var(--paper-2); border: 1px solid var(--line);
    border-radius: var(--r-sm); padding: 12px;
  }
  .audio-col { display: flex; flex-direction: column; gap: 5px; }
  .audio-lbl { font-size: 11px; color: var(--ink-soft); font-weight: 600; letter-spacing: 0.04em; }
  .audio-ta {
    width: 100%; resize: vertical; font-size: 13.5px; line-height: 1.55;
    background: var(--card); border-color: var(--line-2);
  }

  /* L3 — Planos */
  .shots { display: flex; flex-direction: column; gap: 7px; }
  .shot {
    border: 1px solid var(--line); border-left: 3px solid var(--blue);
    border-radius: 0 var(--r-sm) var(--r-sm) 0;
    padding: 9px 11px; background: var(--paper);
  }
  .shot-h { display: flex; align-items: center; gap: 8px; }
  .ptag {
    background: var(--blue); color: #fff; border-radius: var(--r-sm);
    padding: 1px 8px; font-size: 11px; font-weight: 700; flex-shrink: 0; letter-spacing: 0.04em;
  }
  .fr-in {
    flex: 1; font-size: 13.5px; padding: 4px 8px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .fr-in:focus { background: var(--card); }
  .num-in {
    width: 52px; text-align: right; font-family: var(--font-mono); padding: 4px 6px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .num-in:focus { background: var(--card); }
  .s { font-size: 12px; }
  /* Botón de audio colapsable por plano */
  .audio-tog {
    width: 26px; height: 26px; padding: 0; flex-shrink: 0;
    background: var(--paper); border: 1px solid var(--line-2);
    border-radius: var(--r-sm); font-size: 13px; color: var(--ink-soft); box-shadow: none;
  }
  .audio-tog:hover { background: var(--blue-wash); color: var(--blue-deep); border-color: var(--blue); }
  .audio-tog.open { background: var(--blue-wash); color: var(--blue-deep); border-color: var(--blue); }
  /* Sub-campos de audio del plano */
  .shot-audio {
    display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap;
    padding-top: 8px; border-top: 1px dashed var(--line);
  }
  .audio-in {
    flex: 1; min-width: 130px; font-size: 12.5px; padding: 4px 8px;
    background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm);
    color: var(--ink-2);
  }
  .beat-in {
    max-width: 240px; font-size: 13px; padding: 3px 8px;
    background: transparent; border-color: var(--line); border-radius: var(--r-sm);
  }
  .beat-in:focus { background: var(--card); }
  .addshot { align-self: flex-start; }

  /* --- Barra de guardado sticky --- */
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
