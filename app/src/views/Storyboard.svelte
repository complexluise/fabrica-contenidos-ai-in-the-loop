<script>
  import { get, put, post, humanError, bufToBase64 } from "../lib/api.js";
  import { studio, goTo, refreshStatus } from "../lib/studio.svelte.js";

  let { slug } = $props();
  let doc   = $state(null);
  let cand  = $state({ keyframes: {}, cast: {}, selections: {} });
  let editing = $state({});      // { [sceneId]: true } tarjetas en modo edicion
  let expanded = $state({});     // { [sceneId]: true } vista detalle en modo lectura
  let expandedAudio = $state({}); // { "sceneId_shotIdx": true } audio por plano
  let error = $state("");
  let msg   = $state("");
  let dirty = $state(false);
  let saving = $state(false);
  let music = $state(null);       // URL del archivo de música cargado
  let musicPrompt = $state("");
  let musicBusy = $state(false);
  let musicErr = $state("");
  let showMusicGen = $state(false);

  $effect(() => {
    if (!slug) return;
    doc = null; error = ""; msg = ""; dirty = false;
    cand = { keyframes: {}, cast: {}, selections: {} };
    editing = {}; expanded = {};

    get(`/api/projects/${slug}`)
      .then((d) => {
        music = d.music || null;
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

  // Devuelve la URL del keyframe elegido para una escena, o null.
  // selections.yaml guarda rutas relativas al directorio del proyecto
  // (ej: "cache/keyframes/abc.png"), no índices. Las convertimos a /files/{slug}/...
  function selectedKf(sceneId) {
    const selPath = cand.selections?.[sceneId];
    if (!selPath) return null;
    return `/files/${slug}/${String(selPath).replace(/\\/g, "/")}`;
  }
  const hasKfCands = (sceneId) => (cand.keyframes?.[sceneId]?.length ?? 0) > 0;

  const hasAudio = (sh) => !!(sh.voiceover || sh.caption || sh.sfx);
  function toggleAudio(sceneId, j, sh) {
    const k = `${sceneId}_${j}`;
    // Calcula el estado VISIBLE actual (igual que la expresion en el template)
    const currentOpen = expandedAudio[k] !== false && (!!expandedAudio[k] || hasAudio(sh));
    expandedAudio = { ...expandedAudio, [k]: !currentOpen };
  }

  function toggleExpand(id) {
    expanded = { ...expanded, [id]: !expanded[id] };
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

  async function uploadMusic(fileInput) {
    const file = fileInput.files[0];
    if (!file) return;
    musicErr = ""; musicBusy = true;
    try {
      const buf = await file.arrayBuffer();
      const r = await post(`/api/projects/${slug}/music/upload`,
        { data: bufToBase64(buf), filename: file.name });
      music = r.url;
    } catch (e) {
      musicErr = humanError(e);
    } finally {
      musicBusy = false;
      fileInput.value = "";
    }
  }

  async function generateMusic() {
    if (!musicPrompt.trim()) return;
    musicErr = ""; musicBusy = true;
    try {
      const job = await post(`/api/projects/${slug}/music/generate`,
        { prompt: musicPrompt, duration_s: total || 30 });
      // Poll until done
      let done = false;
      while (!done) {
        await new Promise(r => setTimeout(r, 2500));
        const j = await get(`/api/jobs/${job.job_id}`);
        if (j.status === "done") { music = j.result?.url || null; done = true; }
        else if (j.status === "error") { musicErr = j.error || "Error generando musica"; done = true; }
      }
    } catch (e) {
      musicErr = humanError(e);
    } finally {
      musicBusy = false;
    }
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

  <section class="card pad music-card">
    <span class="lbl">Musica de fondo</span>
    {#if music}
      <audio class="music-player" src={music} controls></audio>
      <span class="music-name muted">{music.split("/").pop()}</span>
    {:else}
      <span class="muted music-empty">Sin musica — subí un archivo o generá con IA</span>
    {/if}
    <div class="music-actions">
      <label class="btn small ghost music-upload-lbl" class:disabled={musicBusy}>
        {musicBusy ? "..." : "Subir archivo"}
        <input type="file" accept="audio/*" class="hidden-input"
               onchange={(e) => uploadMusic(e.target)} disabled={musicBusy} />
      </label>
      <button class="small ghost" onclick={() => { showMusicGen = !showMusicGen; musicErr = ""; }}
              disabled={musicBusy}>
        {showMusicGen ? "Cancelar" : "Generar con IA"}
      </button>
    </div>
    {#if showMusicGen}
      <div class="music-gen">
        <input class="music-prompt-in" bind:value={musicPrompt} disabled={musicBusy}
               placeholder="ej: upbeat electronic cumbia, bright and energetic" />
        <button class="small machine" onclick={generateMusic}
                disabled={musicBusy || !musicPrompt.trim()}>
          {musicBusy ? "Generando…" : "Generar"}
        </button>
      </div>
    {/if}
    {#if musicErr}<p class="music-err">{musicErr}</p>{/if}
  </section>

  <div class="toolbar">
    <h2>Escenas</h2>
    <span class="spacer"></span>
    <button class="small ghost" onclick={addScene}>+ Agregar escena</button>
  </div>

  {#each doc.scenes as s, i (s.id)}
    {@const isEditing = !!editing[s.id]}
    {@const isExpanded = !!expanded[s.id]}
    {@const kfUrl = selectedKf(s.id)}
    {@const hasCands = hasKfCands(s.id)}

    <section class="scene" class:is-editing={isEditing}>

      <!-- Cabecera: siempre visible -->
      <div class="shead" class:clickable={!isEditing}
           onclick={!isEditing ? () => toggleExpand(s.id) : null}>
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
        {#if !isEditing}
          <span class="expand-hint muted">{isExpanded ? "▲" : "▼"}</span>
        {/if}
        <span class="spacer"></span>
        <button class="icon" title="Subir" onclick={(e) => { e.stopPropagation(); move(i, -1); }} disabled={i === 0}>↑</button>
        <button class="icon" title="Bajar" onclick={(e) => { e.stopPropagation(); move(i, 1); }} disabled={i === doc.scenes.length - 1}>↓</button>
        <button class="icon danger" title="Eliminar escena" onclick={(e) => { e.stopPropagation(); deleteScene(i); }}>✕</button>
        <button class="small {isEditing ? 'primary' : 'ghost'} edit-btn"
                onclick={(e) => { e.stopPropagation(); toggleEdit(s.id); }}>
          {isEditing ? (dirty ? "Guardar" : "Listo") : "Editar"}
        </button>
      </div>

      {#if isEditing}
        <!-- MODO EDICIÓN: narrativa → planos → prompt IA (colapsable) -->
        <div class="sbody">

          <!-- Dialogo y ambience de la escena -->
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
              {@const audioOpen = expandedAudio[ak] !== false && (!!expandedAudio[ak] || hasAudio(sh))}
              <div class="shot">
                <div class="shot-h">
                  <span class="ptag">P{j + 1}</span>
                  <input class="fr-in" bind:value={sh.framing} oninput={touch} placeholder="encuadre / acción" />
                  <input class="num-in" type="number" min="1" step="1" bind:value={sh.duration_s} oninput={touch} />
                  <span class="muted s">s</span>
                  <button class="audio-tog" class:open={audioOpen}
                          onclick={() => toggleAudio(s.id, j, sh)}
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

          <!-- Panel colapsable "Para la IA": prompt visual tecnico -->
          <details class="ia-section">
            <summary class="ia-toggle">Para la IA — prompt visual <span class="ia-hint">(tecnico)</span></summary>
            <div class="ia-body">
              <span class="lbl small-lbl">Descripcion visual para el modelo de imagen</span>
              <textarea class="prompt-in ia-prompt" bind:value={s.prompt} oninput={touch} rows="3"
                        placeholder="setting + personajes + accion fisica. Lo que la camara VE. Sin dialogo."></textarea>
            </div>
          </details>
        </div>

      {:else}
        <!-- MODO LECTURA -->
        {#if !isExpanded}
          <!-- COLAPSADO: resumen compacto, click para expandir -->
          <div class="read-compact" onclick={() => toggleExpand(s.id)} role="button" tabindex="0">
            <div class="read-compact-text">
              {#if s.dialogue}
                <p class="scene-preview italic">{s.dialogue.length > 95 ? s.dialogue.slice(0, 95) + "…" : s.dialogue}</p>
              {:else if s.shots[0]?.voiceover}
                <p class="scene-preview">{s.shots[0].voiceover.length > 95 ? s.shots[0].voiceover.slice(0, 95) + "…" : s.shots[0].voiceover}</p>
              {:else if s.ambience}
                <p class="scene-preview muted-text">{s.ambience.length > 95 ? s.ambience.slice(0, 95) + "…" : s.ambience}</p>
              {:else}
                <p class="scene-preview muted-text">Sin dialogo ni voz — editá para agregar</p>
              {/if}
              <div class="shots-chips">
                {#each s.shots as sh, j}
                  <span class="chip">
                    <span class="chip-n">P{j + 1}</span>
                    <span class="chip-dur">{sh.duration_s}s</span>
                    {#if sh.sfx}<span class="chip-sfx" title={sh.sfx}>♪</span>{/if}
                    {#if sh.voiceover}<span class="chip-vo" title={sh.voiceover}>vo</span>{/if}
                    {#if sh.caption}<span class="chip-vo" title={sh.caption}>cc</span>{/if}
                  </span>
                {/each}
              </div>
            </div>
            {#if kfUrl}
              <img class="kf-mini" src={kfUrl} alt="keyframe {s.id}" />
            {:else}
              <div class="kf-mini empty-mini">
                <span class="muted" style="font-size:11px">{hasCands ? "candidatos" : "sin kf"}</span>
              </div>
            {/if}
          </div>

        {:else}
          <!-- EXPANDIDO: contenido narrativo (beat, dialogo, VO, ambience, planos) -->
          <div class="read-full">

            <!-- Dialogo de la escena -->
            {#if s.dialogue || s.ambience}
              <div class="rf-section rf-audio-grid">
                {#if s.dialogue}
                  <div class="rf-audio-col">
                    <span class="rf-lbl">Dialogo</span>
                    <p class="rf-dialogue">{s.dialogue}</p>
                  </div>
                {/if}
                {#if s.ambience}
                  <div class="rf-audio-col">
                    <span class="rf-lbl">Ambience / lugar</span>
                    <p class="rf-ambience">{s.ambience}</p>
                  </div>
                {/if}
              </div>
            {/if}

            <!-- Planos: duracion + VO + caption + sfx (sin framing tecnico) -->
            <div class="rf-section">
              <span class="rf-lbl">Planos</span>
              <div class="rf-shots">
                {#each s.shots as sh, j}
                  <div class="rf-shot">
                    <div class="rf-shot-h">
                      <span class="ptag">P{j + 1}</span>
                      <span class="rf-dur mono">{sh.duration_s}s</span>
                    </div>
                    {#if sh.sfx || sh.voiceover || sh.caption}
                      <div class="rf-cues">
                        {#if sh.voiceover}
                          <span class="rf-cue vo-cue"><span class="cue-tag">vo</span>{sh.voiceover}</span>
                        {/if}
                        {#if sh.caption}
                          <span class="rf-cue cc-cue"><span class="cue-tag">cc</span>{sh.caption}</span>
                        {/if}
                        {#if sh.sfx}
                          <span class="rf-cue sfx-cue"><span class="cue-tag">sfx</span>{sh.sfx}</span>
                        {/if}
                      </div>
                    {:else}
                      <p class="rf-noaudio muted">Sin VO ni caption</p>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>

            <!-- Keyframe -->
            <div class="rf-kf-row">
              {#if kfUrl}
                <img class="rf-thumb" src={kfUrl} alt="keyframe {s.id}" />
                <button class="small ghost" onclick={() => goTo("elegir")}>Cambiar →</button>
              {:else if hasCands}
                <span class="muted" style="font-size:12px">◈ candidatos listos —</span>
                <button class="small machine" onclick={() => goTo("elegir")}>Elegir →</button>
              {:else}
                <span class="muted" style="font-size:12px">◇ sin keyframe —</span>
                <button class="small ghost" onclick={() => goTo("elegir")}>Generar →</button>
              {/if}
            </div>

          </div>
        {/if}
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
  .shead.clickable { cursor: pointer; }
  .shead.clickable:hover { background: color-mix(in srgb, var(--paper-2) 80%, var(--blue) 20%); }
  .expand-hint { font-size: 11px; flex-shrink: 0; }
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

  /* --- MODO LECTURA COLAPSADO --- */
  .read-compact {
    display: flex; align-items: stretch; gap: 0;
    cursor: pointer; transition: background 0.12s;
  }
  .read-compact:hover { background: var(--paper-2); }
  .read-compact-text {
    flex: 1; padding: 13px 18px; display: flex; flex-direction: column; gap: 8px;
  }
  .prompt-preview {
    font-size: 13px; line-height: 1.65; color: var(--ink-2); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .shots-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--paper-2); border: 1px solid var(--line);
    border-radius: 999px; padding: 2px 10px; font-size: 11.5px; color: var(--ink-2);
  }
  .chip-n { font-family: var(--font-mono); font-weight: 700; color: var(--blue-deep); font-size: 11px; }
  .chip-fr { color: var(--ink-2); }
  .chip-dur { font-family: var(--font-mono); color: var(--ink-soft); font-size: 11px; }
  .chip-sfx { color: var(--blue-deep); font-size: 11px; }
  .chip-vo { color: var(--ink-soft); font-size: 10px; font-weight: 600; letter-spacing: 0.04em; }
  .kf-mini {
    width: 140px; flex-shrink: 0; object-fit: cover; border-left: 1px solid var(--line);
    display: block;
  }
  .empty-mini {
    width: 140px; flex-shrink: 0; background: var(--paper-2);
    border-left: 1px solid var(--line); display: flex;
    align-items: center; justify-content: center;
  }

  /* --- MODO LECTURA EXPANDIDO --- */
  .read-full { padding: 0 18px 18px; display: flex; flex-direction: column; gap: 0; }
  .rf-section {
    padding: 14px 0; border-bottom: 1px solid var(--line);
    display: flex; flex-direction: column; gap: 8px;
  }
  .rf-section:last-of-type { border-bottom: none; }
  .rf-lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: var(--ink-soft);
  }
  .rf-prompt {
    font-size: 14px; line-height: 1.72; color: var(--ink); margin: 0;
  }

  /* L2: Diálogo + Ambience */
  .rf-audio-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .rf-audio-col { display: flex; flex-direction: column; gap: 4px; }
  .rf-dialogue {
    font-size: 13px; line-height: 1.6; color: var(--ink-2); margin: 0;
    font-style: italic; border-left: 2.5px solid var(--line-2); padding-left: 10px;
  }
  .rf-ambience {
    font-size: 12.5px; line-height: 1.55; color: var(--ink-soft); margin: 0;
  }

  /* L3: Planos */
  .rf-shots { display: flex; flex-direction: column; gap: 9px; }
  .rf-shot {
    border-left: 3px solid var(--blue); padding-left: 12px;
    display: flex; flex-direction: column; gap: 5px;
  }
  .rf-shot-h { display: flex; align-items: center; gap: 10px; }
  .rf-framing { font-size: 13.5px; color: var(--ink); flex: 1; }
  .rf-dur { font-size: 12px; color: var(--ink-soft); }
  .rf-cues { display: flex; flex-direction: column; gap: 3px; padding-left: 2px; }
  .rf-cue { font-size: 12px; color: var(--ink-2); display: flex; gap: 8px; align-items: baseline; }
  .cue-tag {
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--ink-soft); min-width: 22px;
  }
  .sfx-cue .cue-tag { color: var(--blue-deep); }
  .vo-cue .cue-tag  { color: var(--ink-soft); }
  .cc-cue .cue-tag  { color: var(--ink-soft); }

  /* Keyframe en modo expandido */
  .rf-kf-row {
    padding-top: 14px; display: flex; align-items: center; gap: 12px;
  }
  .rf-thumb {
    height: 80px; border-radius: var(--r-sm);
    border: 1px solid var(--line-2); object-fit: cover;
    aspect-ratio: 16 / 9; display: block;
  }

  /* Boton expand en cabecera */

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

  /* --- Modo lectura: contenido narrativo --- */
  .scene-preview {
    font-size: 13px; line-height: 1.65; color: var(--ink-2); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .scene-preview.italic { font-style: italic; border-left: 2px solid var(--line-2); padding-left: 8px; }
  .scene-preview.muted-text { color: var(--ink-soft); }
  .rf-noaudio { font-size: 12px; margin: 0; }

  /* --- Panel "Para la IA" (colapsable en modo edicion) --- */
  .ia-section {
    border-top: 1px dashed var(--line); margin-top: 6px;
  }
  .ia-toggle {
    cursor: pointer; list-style: none; padding: 9px 2px;
    font-size: 11px; font-weight: 700; color: var(--ink-soft);
    text-transform: uppercase; letter-spacing: 0.10em;
    display: flex; align-items: center; gap: 6px;
  }
  .ia-toggle::-webkit-details-marker { display: none; }
  .ia-toggle::before { content: "▶"; font-size: 9px; transition: transform 0.15s; }
  details[open] > .ia-toggle::before { transform: rotate(90deg); }
  .ia-hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--ink-soft); }
  .ia-body { padding: 8px 0 4px; display: flex; flex-direction: column; gap: 6px; }
  .ia-prompt { border-color: var(--line); background: var(--paper); }
  .small-lbl { font-size: 10px; }

  /* --- Musica de fondo --- */
  .music-card { display: flex; flex-direction: column; gap: 10px; }
  .music-player { width: 100%; height: 36px; }
  .music-name { font-size: 11.5px; }
  .music-empty { font-size: 13px; }
  .music-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .music-upload-lbl {
    display: inline-flex; align-items: center; cursor: pointer;
  }
  .music-upload-lbl.disabled { opacity: 0.5; pointer-events: none; }
  .hidden-input { display: none; }
  .music-gen { display: flex; gap: 8px; align-items: center; }
  .music-prompt-in {
    flex: 1; font-size: 13px; padding: 5px 10px;
    background: var(--paper-2); border-color: var(--line); border-radius: var(--r-sm);
  }
  .music-err { color: var(--red); font-size: 12.5px; margin: 0; }
</style>
