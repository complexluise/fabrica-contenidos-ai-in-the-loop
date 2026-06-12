# -*- coding: utf-8 -*-
"""D-081b: terminar la adopcion + utilidades globales + StageNode/JobLog + goTo muertos."""
import io
import re


def load(p): return io.open(p, encoding='utf-8').read()
def save(p, s): io.open(p, 'w', encoding='utf-8').write(s)


def rep(src, old, new, path=""):
    assert old in src, "%s NOT FOUND: %r" % (path, old[:90])
    return src.replace(old, new)


def sub1(src, pattern, repl, path=""):
    out, n = re.subn(pattern, repl, src, count=1, flags=re.S)
    assert n == 1, "%s REGEX NOT FOUND: %r" % (path, pattern[:80])
    return out


def viewheader(src, path):
    """<header class=head>...</header> -> <ViewHeader> (el lede como children)."""
    pat = r'<header class="head">\s*<div class="eyebrow">(.*?)</div>\s*<h1>(.*?)</h1>\s*<p class="lede[^"]*">\s*(.*?)\s*</p>\s*</header>'
    m = re.search(pat, src, re.S)
    assert m, "%s: header no encontrado" % path
    new = '<ViewHeader eyebrow="%s" title="%s">\n  %s\n</ViewHeader>' % (m.group(1), m.group(2), m.group(3))
    return src[:m.start()] + new + src[m.end():]


def drop_css(src, *rules):
    """Borra reglas CSS de una linea o bloque {...} simple por nombre exacto de selector."""
    for sel in rules:
        pat = r'\n  ' + re.escape(sel) + r' \{[^}]*\}'
        src, n = re.subn(pat, '', src, count=1, flags=re.S)
        assert n == 1, "CSS NOT FOUND: %r" % sel
    return src


# ================= app.css: utilidades compartidas =================
p = 'app/src/app.css'
s = load(p)
s = s.rstrip() + '''

/* --- utilidades compartidas (D-081): pixeles comunes, UNA sola vez --------- */
.muted { color: var(--ink-soft); }
.empty { padding: 30px; text-align: center; margin-top: 16px; }
.empty p { margin: 4px 0; }
.note { background: var(--paper-2); border: 1px dashed var(--line-2); border-radius: var(--r); padding: 9px 14px; font-size: 14px; }
.group { margin: 14px 0 22px; }
.group-h { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 16px; }
'''
save(p, s)
print('ok app.css')

# ================= components/StageNode.svelte =================
save('app/src/components/StageNode.svelte', '''<script>
  // [D-081] El nodo del bucle (circulo numerado / tick / icono por actor).
  // Estaba duplicado entre la espina del sidebar (App) y las estaciones del
  // Inicio — el mismo lenguaje visual, una sola implementacion.
  let { n = "", actor = "lee", done = false, size = 30, icon = "" } = $props();
</script>

<span class="stage-node actor-{actor}" class:done style="--sz:{size}px">
  {#if done}
    <svg viewBox="0 0 16 16" class="ico"><path d="M3 8.5l3.2 3L13 4.5" fill="none"
      stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
  {:else if icon === "home"}
    <svg viewBox="0 0 16 16" class="ico"><path d="M2.5 7.5L8 3l5.5 4.5V13a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1z"
      fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
  {:else}
    {n}
  {/if}
</span>

<style>
  .stage-node {
    position: relative; z-index: 1; width: var(--sz); height: var(--sz); flex-shrink: 0;
    display: grid; place-items: center; border-radius: 50%;
    border: 2px solid var(--line-2); background: var(--paper);
    font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--ink-soft);
  }
  .ico { width: 16px; height: 16px; }
  .actor-tu { border-color: var(--red); color: var(--red-deep); }
  .actor-ia { border-color: var(--blue); color: var(--blue-deep); }
  .done { background: var(--ok); border-color: var(--ok); color: #fff; }
</style>
''')
print('ok StageNode')

# ================= components/JobLog.svelte =================
save('app/src/components/JobLog.svelte', '''<script>
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
''')
print('ok JobLog')

# ================= App.svelte: StageNode + pulse global =================
p = 'app/src/App.svelte'
s = load(p)
s = rep(s, 'import Inicio from "./views/Inicio.svelte";',
        'import StageNode from "./components/StageNode.svelte";\n  import Inicio from "./views/Inicio.svelte";', p)
s = rep(s, '''          <span class="node">
            {#if state === "done"}
              <svg viewBox="0 0 16 16" class="tick"><path d="M3 8.5l3.2 3L13 4.5"
                fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"
                stroke-linejoin="round"/></svg>
            {:else if s.id === "inicio"}
              <svg viewBox="0 0 16 16" class="home"><path d="M2.5 7.5L8 3l5.5 4.5V13a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1z"
                fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
            {:else}
              {s.n}
            {/if}
          </span>''',
        '          <StageNode n={s.n} actor={s.actor} done={state === "done"}\n'
        '                     icon={s.id === "inicio" ? "home" : ""} />', p)
s = drop_css(s, '.node', '.step.actor-tu .node', '.step.actor-ia .node', '.step.state-done .node')
s = rep(s, '  .tick, .home { width: 16px; height: 16px; }\n', '', p)
s = rep(s, '''  /* paso actual = anillo pulsante */
  .step.current .node { animation: pulse 1.8s ease-in-out infinite; }''',
        '''  /* paso actual = anillo pulsante */
  .step.current :global(.stage-node) { animation: sb-pulse 1.8s ease-in-out infinite; }''', p)
s = rep(s, '''  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(214, 64, 42, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(214, 64, 42, 0); }
  }''',
        '''  @keyframes -global-sb-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(214, 64, 42, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(214, 64, 42, 0); }
  }''', p)
save(p, s)
print('ok App')

# ================= Inicio: WarnStrip + StageNode + CSS fuera =================
p = 'app/src/views/Inicio.svelte'
s = load(p)
s = rep(s, 'import { onMount } from "svelte";',
        'import { onMount } from "svelte";\n  import StageNode from "../components/StageNode.svelte";\n  import WarnStrip from "../components/WarnStrip.svelte";', p)
s = rep(s, '''{#if st && !st.keys?.fal_key}
  <div class="warn-strip">
    <b>Primero: configurá tus claves.</b> Sin la clave de fal.ai no se puede generar nada.
    <button class="small" onclick={() => goTo("ajustes")}>Ir a Configuración →</button>
  </div>
{/if}''',
        '''{#if st && !st.keys?.fal_key}
  <WarnStrip actionLabel="Ir a Configuración →" onaction={() => goTo("ajustes")}>
    <b>Primero: configurá tus claves.</b> Sin la clave de fal.ai no se puede generar nada.
  </WarnStrip>
{/if}''', p)
s = rep(s, '<span class="num actor-{s.actor}">{done ? "✓" : s.n}</span>',
        '<StageNode n={s.n} actor={s.actor} {done} size={28} />', p)
s = drop_css(s, '.warn-strip', '.num', '.num.actor-tu', '.num.actor-ia', '.station.done .num')
s = rep(s, '  .warn-strip button { margin-left: auto; }\n', '', p)
s = rep(s, '  .station.done .num { background: var(--ok); border-color: var(--ok); color: #fff; }\n', '', p) if '.station.done .num {' in s else s
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Inicio')

# ================= Importar: ViewHeader + WarnStrip + JobLog =================
p = 'app/src/views/Importar.svelte'
s = load(p)
s = rep(s, 'import { jobState } from "../lib/jobs.svelte.js";',
        'import { jobState } from "../lib/jobs.svelte.js";\n  import JobLog from "../components/JobLog.svelte";\n  import ViewHeader from "../components/ViewHeader.svelte";\n  import WarnStrip from "../components/WarnStrip.svelte";', p)
s = viewheader(s, p)
s = rep(s, '''{#if noKey}
  <div class="warn-strip">
    <b>Falta la clave de Anthropic.</b> La descomposición usa Claude.
    <button class="small" onclick={() => goTo("ajustes")}>Ir a Ajustes →</button>
  </div>
{/if}''',
        '''{#if noKey}
  <WarnStrip actionLabel="Ir a Ajustes →" onaction={() => goTo("ajustes")}>
    <b>Falta la clave de Anthropic.</b> La descomposición usa Claude.
  </WarnStrip>
{/if}''', p)
s = rep(s, '''{#if imp.log.length}
  <pre class="log">{imp.log.join("\\n")}</pre>
{/if}''',
        '''{#if imp.busy || imp.log.length}
  <JobLog log={imp.log} />
{/if}''', p)
s = drop_css(s, '.head', '.head h1', '.lede', '.warn-strip', '.log')
s = rep(s, '  .warn-strip button { margin-left: auto; }\n', '', p)
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Importar')

# ================= Produccion: ViewHeader + WarnStrip + JobLog =================
p = 'app/src/views/Produccion.svelte'
s = load(p)
s = rep(s, 'import { jobState } from "../lib/jobs.svelte.js";',
        'import { jobState } from "../lib/jobs.svelte.js";\n  import JobLog from "../components/JobLog.svelte";\n  import ViewHeader from "../components/ViewHeader.svelte";\n  import WarnStrip from "../components/WarnStrip.svelte";', p)
s = viewheader(s, p)
s = rep(s, '''{#if !ready && !renderDone}
  <div class="warn-strip">
    <b>Te faltan elecciones.</b> Confirmá los encuadres de cada escena antes de renderizar.
    <button class="small" onclick={() => goTo("encuadres")}>Ir a Encuadres</button>
  </div>
{/if}''',
        '''{#if !ready && !renderDone}
  <WarnStrip actionLabel="Ir a Encuadres" onaction={() => goTo("encuadres")}>
    <b>Te faltan elecciones.</b> Confirmá los encuadres de cada escena antes de renderizar.
  </WarnStrip>
{/if}''', p)
s = rep(s, '''<div class="log-wrap">
  <button class="log-toggle eyebrow" onclick={() => (showLog = !showLog)}>
    {showLog ? "▾" : "▸"} Registro en vivo
  </button>
  {#if showLog}
    <div class="log mono">
      {#if cur.log.length === 0}
        <span class="muted">El progreso aparece aca mientras la maquina trabaja…</span>
      {:else}
        {#each cur.log as l}<div>{l}</div>{/each}
      {/if}
    </div>
  {/if}
</div>''', '<JobLog log={cur.log} />', p)
s = rep(s, '  let showLog = $state(true);\n', '', p)
s = drop_css(s, '.head', '.head h1', '.lede', '.lede span[title]', '.warn-strip',
             '.log-wrap', '.log-toggle', '.log-toggle:hover', '.log')
s = rep(s, '  .warn-strip button { margin-left: auto; }\n', '', p)
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Produccion')

# ================= Animatic: ViewHeader + CSS fuera =================
p = 'app/src/views/Animatic.svelte'
s = load(p)
s = rep(s, 'import Progress from "../components/Progress.svelte";',
        'import Progress from "../components/Progress.svelte";\n  import ViewHeader from "../components/ViewHeader.svelte";', p)
s = viewheader(s, p)
s = drop_css(s, '.head', '.head h1', '.lede', '.lede .r')
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Animatic')

# ================= Ajustes: ViewHeader + CSS fuera =================
p = 'app/src/views/Ajustes.svelte'
s = load(p)
s = rep(s, 'import { onMount } from "svelte";',
        'import { onMount } from "svelte";\n  import ViewHeader from "../components/ViewHeader.svelte";', p)
s = viewheader(s, p)
s = drop_css(s, '.head', '.head h1', '.lede')
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p) if '.muted { color: var(--ink-soft); }\n' in s else s
save(p, s)
print('ok Ajustes')

# ================= Casting / Encuadres: utilidades ya globales =================
p = 'app/src/views/Casting.svelte'
s = load(p)
s = drop_css(s, '.note', '.group', '.group-h', '.empty', '.empty p')
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Casting')

p = 'app/src/views/Encuadres.svelte'
s = load(p)
s = drop_css(s, '.note', '.group', '.group-h', '.empty', '.empty p')
s = rep(s, '  .muted { color: var(--ink-soft); }\n', '', p)
save(p, s)
print('ok Encuadres')

# ================= Storyboard: los goTo("elegir") MUERTOS (D-080 los perdio) ===
p = 'app/src/views/Storyboard.svelte'
s = load(p)
s = rep(s, 'import { studio, goTo, refreshStatus } from "../lib/studio.svelte.js";',
        'import { studio, goTo, refreshStatus, nextStep } from "../lib/studio.svelte.js";', p)
s = rep(s, '<button class="small ghost" onclick={() => goTo("elegir")}>Cambiar →</button>',
        '<button class="small ghost" onclick={() => goTo("encuadres")}>Cambiar →</button>', p)
s = rep(s, '<button class="small machine" onclick={() => goTo("elegir")}>Elegir →</button>',
        '<button class="small machine" onclick={() => goTo("encuadres")}>Elegir →</button>', p)
s = rep(s, '<button class="small ghost" onclick={() => goTo("elegir")}>Generar →</button>',
        '<button class="small ghost" onclick={() => goTo("encuadres")}>Generar →</button>', p)
s = rep(s, '<button class="primary cta go" onclick={() => goTo("elegir")}>Siguiente: Elegir →</button>',
        '<button class="primary cta go" onclick={() => goTo(nextStep(studio.status)?.tab || "casting")}>Siguiente paso →</button>', p)
save(p, s)
print('ok Storyboard')

print('trim ok')
