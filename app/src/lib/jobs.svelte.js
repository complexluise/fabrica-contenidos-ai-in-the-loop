// [D-081] El ciclo de vida de UN job, una sola vez.
// Antes el patron busy/progress/err/log + runJob estaba copiado OCHO veces en
// las vistas — y la musica estuvo siempre rota porque una copia divergio
// (job_id inexistente + estado "error" vs "failed", D-080). Una implementacion,
// imposible divergir.
import { attachJob, get, runJob, humanError } from "./api.js";

/**
 * Crea el estado reactivo de un job. Uso:
 *   const gen = jobState();
 *   gen.run(`/api/.../keyframes?n=2`, { onDone: load });
 *   {#if gen.busy}<Progress text={gen.progress} />{/if}
 *
 * `key` distingue trabajos del mismo jobState (p.ej. "scene:s1" para el boton
 * por-escena): `gen.busy && gen.key === "scene:s1"`.
 */
export function jobState() {
  const j = $state({
    busy: false,
    key: "",        // que trabajo concreto esta corriendo (opcional)
    status: "",     // "" | "running" | "done" | "failed" | "error"
    progress: "",   // ultima linea del log (para el spinner)
    log: [],        // todas las lineas (para el registro en vivo)
    err: "",
  });

  const begin = (key, keepLog) => {
    j.busy = true;
    j.key = key;
    j.status = "running";
    j.err = "";
    j.progress = "";
    if (!keepLog) j.log.length = 0;
  };
  const handlers = (onLine, onDone) => ({
    onLine: (l) => {
      j.progress = l;
      j.log.push(l);
      onLine?.(l);
    },
    onDone: async (status, jobId) => {
      j.busy = false;
      j.key = "";
      j.status = status;
      if (status !== "done") j.err = `Terminó como: ${status}. Revisá el registro.`;
      await onDone?.(status, jobId);
    },
    onError: (e) => {
      j.busy = false;
      j.key = "";
      j.status = "error";
      j.err = humanError(e);
    },
  });

  j.run = (path, { body, key = "", keepLog = false, onLine, onDone } = {}) => {
    begin(key, keepLog);
    runJob(path, { body, ...handlers(onLine, onDone) });
  };

  // [T2.6.8] Re-engancharse a un job que YA corre en el server (tras F5 o
  // cierre del SSE): repuebla busy/log/progress — el stream hace replay.
  j.attach = (jobId, { key = "", onLine, onDone } = {}) => {
    begin(key, false);
    attachJob(jobId, handlers(onLine, onDone));
  };

  return j;
}

// [T2.6.9] "¿Quedó un job vivo de los míos?" — para que F5 a mitad de una
// generación no muestre la UI ociosa (y un segundo clic pague dos veces).
// `kinds`: kinds del server que esta vista dispara. `slug`: el proyecto ("" =
// sin filtro, p.ej. Importar). El project del job puede ser "slug" o
// "slug/sub" (jobs por escena/pose). Devuelve el job o null.
export async function findLiveJob(kinds, slug = "") {
  try {
    const all = await get("/api/jobs");
    return all.find((job) =>
      kinds.includes(job.kind)
      && (job.status === "running" || job.status === "queued")
      && (!slug || job.project === slug || job.project.startsWith(slug + "/"))
    ) ?? null;
  } catch {
    return null; // sin lista de jobs no hay re-enganche, pero tampoco rotura
  }
}

// --- [Fase 3 / D-083] Monitor GLOBAL de jobs ---------------------------------
// Un dashboard siempre visible: TODOS los jobs activos con su progreso, sin
// importar en qué vista estés. Descubre jobs nuevos polleando /api/jobs (barato,
// sin logs) y sigue el progreso de cada uno por SSE (replay desde la línea 0).
// Coexiste con el re-enganche por vista (T2.6.9) gracias al stream multi-
// consumidor (T2.6.23): la misma generación alimenta el dock y su pantalla.
export const jobsMonitor = $state({ items: {} });  // id -> {id,kind,project,progress,status}

const _streams = new Map();   // id -> cancel()
let _pollTimer = null;

function _drop(id, delay = 0) {
  const cancel = _streams.get(id);
  if (cancel) { cancel(); _streams.delete(id); }
  if (delay) setTimeout(() => { delete jobsMonitor.items[id]; }, delay);
  else delete jobsMonitor.items[id];
}

function _watch(job) {
  jobsMonitor.items[job.id] = {
    id: job.id, kind: job.kind, project: job.project,
    progress: "", status: job.status,
  };
  const cancel = attachJob(job.id, {
    onLine: (l) => { const it = jobsMonitor.items[job.id]; if (it) it.progress = l; },
    onDone: (status) => {
      const it = jobsMonitor.items[job.id];
      if (it) { it.status = status; if (status !== "done") it.progress = "terminó con error"; }
      // dejar el desenlace visible un instante (✓ rápido, error más tiempo).
      _drop(job.id, status === "done" ? 1800 : 4500);
    },
    onError: () => _drop(job.id, 0),
  });
  _streams.set(job.id, cancel);
}

export function startJobsMonitor() {
  if (_pollTimer || typeof window === "undefined") return;
  const tick = async () => {
    let all;
    try { all = await get("/api/jobs"); } catch { return; }
    for (const j of all) {
      if ((j.status === "running" || j.status === "queued") && !_streams.has(j.id)) {
        _watch(j);  // job nuevo (de cualquier vista): engancharse a su progreso
      }
    }
  };
  tick();
  _pollTimer = setInterval(tick, 3000);
}

export function stopJobsMonitor() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  for (const id of [..._streams.keys()]) _drop(id, 0);
}
