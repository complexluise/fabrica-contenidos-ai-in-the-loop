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
