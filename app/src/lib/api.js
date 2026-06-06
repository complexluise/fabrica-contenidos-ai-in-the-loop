// Helpers de fetch contra la API del Studio (mismo origen en build; proxy en dev).

async function req(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const get = (path) => req(path);

export const post = (path, body) =>
  req(path, {
    method: "POST",
    headers: body ? { "content-type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });

export const put = (path, body) =>
  req(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

// Traduce un error crudo (texto del backend o traceback) a algo legible por humanos.
export function humanError(e) {
  const raw = (e && e.message ? e.message : String(e || "")).trim();
  if (!raw) return "Algo falló. Revisá el progreso de abajo.";
  if (/FAL_KEY|fal[_ ]?key|401|403|unauthor/i.test(raw))
    return "Parece un problema con la clave de fal.ai. Revisala en Ajustes.";
  if (/ANTHROPIC/i.test(raw)) return "Falta o falla la clave de Anthropic (Ajustes).";
  if (/ECONNREFUSED|Failed to fetch|NetworkError/i.test(raw))
    return "No hay conexión con el motor. ¿Está corriendo 'pipeline studio'?";
  // Si vino un traceback, quedate con la ultima linea (el mensaje real).
  const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
  const last = lines[lines.length - 1] || raw;
  return last.length > 200 ? last.slice(0, 200) + "…" : last;
}

// Dispara un job (POST) y transmite su progreso por SSE.
// onLine(line), onDone(status) — devuelve una función para cancelar.
export async function runJob(postPath, { onLine, onDone, onError } = {}) {
  let es;
  try {
    const job = await post(postPath);
    es = new EventSource(`/api/jobs/${job.id}/stream`);
    es.onmessage = (e) => {
      if (e.data.startsWith("__status__:")) {
        es.close();
        onDone?.(e.data.slice("__status__:".length), job.id);
      } else {
        onLine?.(e.data);
      }
    };
    es.onerror = () => { es.close(); onError?.(); };
  } catch (err) {
    onError?.(err);
  }
  return () => es?.close();
}
