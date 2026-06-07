// Estado compartido del Studio (Svelte 5 runes) + la definicion del BUCLE.
// La filosofia vive aca: cada paso dice QUIEN actua (la IA propone / vos decidis).
import { get } from "./api.js";

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
export const STAGES = [
  { id: "inicio",     n: 0, label: "Inicio",     sub: "Donde estas parado",          actor: "lee" },
  { id: "importar",   n: 1, label: "Importar",   sub: "Texto -> borrador (la IA)",   actor: "ia"  },
  { id: "storyboard", n: 2, label: "Storyboard", sub: "Edita y firma el plan",       actor: "tu"  },
  { id: "elegir",     n: 3, label: "Elegir",     sub: "La IA propone, vos decidis",  actor: "tu"  },
  { id: "producir",   n: 4, label: "Producir",   sub: "Armar el video y el paquete", actor: "ia"  },
];

// Configuración (claves de API): setup transversal, fuera del bucle numerado (#4).
export const CONFIG = { id: "ajustes", label: "Configuración", sub: "Claves de API" };

// Glosario: traducir la jerga a lenguaje humano (se muestra inline).
export const GLOSARIO = {
  keyframe: "imagen base de la que sale cada plano",
  casting: "la cara del personaje, fijada una vez",
  "rough cut": "corte de referencia, no el definitivo",
  plano: "una toma; el video se arma juntando planos",
  storyboard: "el plan: escenas y planos, antes de generar",
};

export const hasProject = () => !!studio.slug && studio.projects.length > 0;

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
  await refreshStatus();
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
  if (typeof window !== "undefined") window.scrollTo({ top: 0 });
}

// El "siguiente paso": una sola recomendacion clara segun el estado real.
// Devuelve { tab, label, why } o null si el bucle esta completo.
export function nextStep(st) {
  if (!hasProject())
    return { tab: "importar", label: "Importar un guion", why: "Empezá pegando o subiendo tu texto." };
  if (!st) return { tab: "ajustes", label: "Configurar claves", why: "Empezá por tus API keys." };
  if (!st.keys?.fal_key)
    return { tab: "ajustes", label: "Configurar las claves", why: "Sin la clave de fal.ai no se puede generar nada." };

  if (!st.storyboard?.signed)
    return { tab: "storyboard", label: "Firmar el plan", why: "Revisá las escenas y firmá el plan antes de generar." };

  const cast = st.casting || {};
  if (cast.needed > 0 && cast.chosen < cast.needed)
    return { tab: "elegir", label: "Elegir la cara del personaje", why: "Fijá el casting antes de los encuadres." };

  const kf = st.keyframes || {};
  if (kf.total > 0 && kf.chosen < kf.total)
    return {
      tab: "elegir",
      label: `Elegir encuadres (${kf.chosen}/${kf.total})`,
      why: "La IA propone candidatos; vos elegís el de cada escena.",
    };

  if (!st.render?.done)
    return { tab: "producir", label: "Armar el video", why: "Ya elegiste todo: la máquina ejecuta." };

  if (!st.export?.done)
    return { tab: "producir", label: "Armar el paquete de edición", why: "Empaquetá para la editora." };

  return null; // bucle completo
}
