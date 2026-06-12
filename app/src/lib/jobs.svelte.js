// [D-081] El ciclo de vida de UN job, una sola vez.
// Antes el patron busy/progress/err/log + runJob estaba copiado OCHO veces en
// las vistas — y la musica estuvo siempre rota porque una copia divergio
// (job_id inexistente + estado "error" vs "failed", D-080). Una implementacion,
// imposible divergir.
import { runJob, humanError } from "./api.js";

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

  j.run = (path, { body, key = "", keepLog = false, onLine, onDone } = {}) => {
    j.busy = true;
    j.key = key;
    j.status = "running";
    j.err = "";
    j.progress = "";
    if (!keepLog) j.log.length = 0;
    runJob(path, {
      body,
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
  };

  return j;
}
