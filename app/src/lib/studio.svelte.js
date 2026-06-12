// Estado compartido del Studio (Svelte 5 runes) + la definicion del BUCLE.
// La filosofia vive aca: cada paso dice QUIEN actua (la IA propone / vos decidis).
import { get, post, del } from "./api.js";

export const studio = $state({
  projects: [],
  slug: "",
  tab: "inicio",
  status: null, // { keys, scenes_total, casting, keyframes, render, export }
  error: "",
});

// Los pasos del bucle, en orden. `actor`: quien tiene la pelota.
//   "tu"  -> la persona prepara/decide   (rojo)
//   "ia"  -> la maquina propone/ejecuta  (azul)
//   "lee" -> lectura/contexto            (neutro)
// Ajustes (claves) NO es un paso del bucle: es setup. Vive aparte (CONFIG, #4).
// D-061: "Elegir" se separa en tres etapas, de lo grueso a lo fino — una página,
// una decisión: Casting (QUIENES) -> Encuadres (como se VE cada escena) ->
// Animatic (como FLUYE la pelicula, en poses, antes de pagar video).
export const STAGES = [
  { id: "inicio",     n: 0, label: "Inicio",     sub: "Donde estas parado",            actor: "lee" },
  { id: "importar",   n: 1, label: "Guion",      sub: "Texto -> borrador (la IA)",     actor: "ia"  },
  { id: "storyboard", n: 2, label: "Storyboard", sub: "Edita y firma el plan",         actor: "tu"  },
  { id: "casting",    n: 3, label: "Casting",    sub: "La cara de cada personaje",     actor: "tu"  },
  { id: "encuadres",  n: 4, label: "Encuadres",  sub: "La imagen clave de cada escena", actor: "tu" },
  { id: "animatic",   n: 5, label: "Animatic",   sub: "La pelicula en poses",          actor: "tu"  },
  { id: "producir",   n: 6, label: "Producir",   sub: "Armar el video y el paquete",   actor: "ia"  },
];

// Configuración (claves de API): setup transversal, fuera del bucle numerado (#4).
export const CONFIG = { id: "ajustes", label: "Configuración", sub: "Claves de API" };

// Glosario: traducir la jerga a lenguaje humano (se muestra inline).
export const GLOSARIO = {
  keyframe: "la imagen clave de la escena: el momento donde el plano ATERRIZA (su destino)",
  casting: "la cara del personaje, fijada una vez",
  animatic: "la pelicula completa en poses (apertura -> destino por plano), antes de pagar video",
  "rough cut": "corte de referencia, no el definitivo",
  plano: "una toma; el video se arma juntando planos",
  storyboard: "el plan: escenas y planos, antes de generar",
};

export const hasProject = () => !!studio.slug && studio.projects.length > 0;

// --- routing por hash (D-081): #/<slug>/<tab>. F5 y el boton atras conservan
// donde estabas; una pestaña se puede compartir. Sin router externo (~25 lineas).
const TABS = new Set([...STAGES.map((s) => s.id), CONFIG.id]);

export function parseHash() {
  if (typeof window === "undefined") return null;
  const m = window.location.hash.match(/^#\/([^/]*)\/([\w-]+)$/);
  if (!m) return null;
  return { slug: decodeURIComponent(m[1]), tab: TABS.has(m[2]) ? m[2] : "inicio" };
}

export function writeHash() {
  if (typeof window === "undefined") return;
  const h = `#/${encodeURIComponent(studio.slug || "")}/${studio.tab}`;
  if (window.location.hash !== h) window.location.hash = h;
}

export function initRouting() {
  if (typeof window === "undefined") return;
  window.addEventListener("hashchange", async () => {
    const w = parseHash();
    if (!w) return;
    if (w.slug && w.slug !== studio.slug && studio.projects.some((p) => p.slug === w.slug)) {
      await setSlug(w.slug);
    }
    if (w.tab !== studio.tab) studio.tab = w.tab;
  });
}

export async function loadProjects() {
  try {
    studio.projects = await get("/api/projects");
    if (!studio.projects.length) {
      studio.slug = "";
      studio.status = null;
      studio.tab = "importar"; // sin proyecto: arranca por Importar (D-033)
      return;
    }
    if (!studio.slug || !studio.projects.some((p) => p.slug === studio.slug)) {
      studio.slug = studio.projects[0].slug;
    }
    await refreshStatus();
  } catch (e) {
    studio.error = String(e);
  }
}

export async function setSlug(slug) {
  studio.slug = slug;
  studio.status = null;
  writeHash();
  await refreshStatus();
}

// Crea un proyecto en blanco y lo abre. Devuelve el slug creado (#3).
export async function createProject(title, style) {
  const r = await post("/api/projects", { title, style });
  await loadProjects();
  await setSlug(r.slug);
  return r.slug;
}

// Borra un proyecto (destructivo) y reubica la selección (#3).
export async function deleteProject(slug) {
  await del(`/api/projects/${slug}`);
  if (studio.slug === slug) studio.slug = "";
  await loadProjects();
}

export async function refreshStatus() {
  if (!studio.slug) return;
  try {
    studio.status = await get(`/api/projects/${studio.slug}/status`);
  } catch {
    studio.status = null;
  }
}

export function goTo(tab) {
  studio.tab = tab;
  writeHash();     // D-081: la URL refleja donde estas (F5/atras funcionan)
  refreshStatus(); // D-080: navegar re-lee el estado (la espina nunca miente)
  if (typeof window !== "undefined") window.scrollTo({ top: 0 });
}

// --- el bucle, derivado del `stage` que decide el MOTOR (D-032) -------------
// El front NO recalcula si un paso esta completo: lee `status.stage` (fuente
// unica) y aca solo mapea ese stage a presentacion (copy + a que pestaña va).
export const PIPELINE_ORDER = ["sin_claves", "guion", "casting", "encuadres", "render", "paquete", "completo"];

// stage -> recomendacion de "siguiente paso" (la copia, no la logica)
const NEXT = {
  sin_claves: { tab: "ajustes",    label: "Configurar FAL_KEY",              why: "Sin la clave de fal.ai no se puede generar nada." },
  guion:      { tab: "storyboard", label: "Firmar el plan",                  why: "Revisá las escenas y firmá el plan antes de generar." },
  casting:    { tab: "casting",    label: "Elegir la cara del personaje",    why: "Fijá el casting antes de los encuadres." },
  encuadres:  { tab: "encuadres",  label: "Elegir encuadres",                why: "La IA propone candidatos; vos elegís el de cada escena." },
  render:     { tab: "animatic",   label: "Revisar el animatic",             why: "Mirá la película en poses antes de gastar en video; si te convence, pasá a Producción." },
  paquete:    { tab: "producir",   label: "Armar el paquete de edición",     why: "Empaquetá para la editora." },
};

// Devuelve { tab, label, why } o null si el bucle esta completo.
export function nextStep(st) {
  if (!hasProject())
    return { tab: "importar", label: "Importar un guion", why: "Empezá pegando o subiendo tu texto." };
  if (!st) return { tab: "ajustes", label: "Configurar claves", why: "Empezá por tus API keys." };
  const meta = NEXT[st.stage];
  if (!meta) return null; // completo
  if (st.stage === "encuadres" && st.keyframes)
    return { ...meta, label: `Elegir encuadres (${st.keyframes.chosen}/${st.keyframes.total})` };
  return meta;
}

// "El paso del sidebar `id` ya esta hecho?" -- segun donde quedo el stage en el orden.
export function stepDone(id, st) {
  if (!st) return false;
  const at = PIPELINE_ORDER.indexOf(st.stage);
  if (id === "ajustes")    return at > PIPELINE_ORDER.indexOf("sin_claves");
  if (id === "importar")   return at > PIPELINE_ORDER.indexOf("guion");
  if (id === "storyboard") return at > PIPELINE_ORDER.indexOf("guion");
  if (id === "casting")    return at > PIPELINE_ORDER.indexOf("casting");
  if (id === "encuadres")  return at > PIPELINE_ORDER.indexOf("encuadres");
  // Animatic: hecho cuando todas las poses estan en cache (o si ya se renderizo).
  if (id === "animatic")
    return (st.animatic && st.animatic.total > 0 && st.animatic.ready >= st.animatic.total)
           || at > PIPELINE_ORDER.indexOf("render");
  if (id === "producir")   return st.stage === "completo";
  return false;
}
