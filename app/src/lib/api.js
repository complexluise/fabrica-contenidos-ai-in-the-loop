// Helpers de fetch contra la API del Studio (mismo origen en build; proxy en dev).

async function req(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let raw = (await r.text()) || r.statusText;
    // FastAPI manda {"detail": "..."} — mostrarle al humano el detalle, no el JSON.
    try {
      const j = JSON.parse(raw);
      if (j && typeof j.detail === "string") raw = j.detail;
    } catch { /* no era JSON: queda el texto crudo */ }
    throw new Error(raw);
  }
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

export const del = (path) => req(path, { method: "DELETE" });

// Convierte un ArrayBuffer a base64 en chunks para evitar "too many function arguments"
// con archivos grandes (el spread ...Uint8Array falla en >~65K bytes en todos los navegadores).
export function bufToBase64(buf) {
  const bytes = new Uint8Array(buf);
  let binary = "";
  const CHUNK = 8192;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

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

// Se suscribe al SSE de un job (nuevo o YA corriendo — el stream del server
// hace replay desde la línea 0, así que F5 no pierde el registro).
export function attachJob(jobId, { onLine, onDone, onError } = {}) {
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  es.onmessage = (e) => {
    if (e.data.startsWith("__status__:")) {
      es.close();
      onDone?.(e.data.slice("__status__:".length), jobId);
    } else {
      onLine?.(e.data);
    }
  };
  es.onerror = () => { es.close(); onError?.(); };
  return () => es.close();
}

// Dispara un job (POST [body]) y transmite su progreso por SSE.
// onLine(line), onDone(status, jobId) — devuelve una función para cancelar.
export async function runJob(postPath, { body, onLine, onDone, onError } = {}) {
  let cancel;
  try {
    const job = await post(postPath, body);
    cancel = attachJob(job.id, { onLine, onDone, onError });
  } catch (err) {
    onError?.(err);
  }
  return () => cancel?.();
}
