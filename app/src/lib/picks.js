// [D-081] Reconciliacion seleccion-en-disco -> indice de candidato. Pura.
// selections.yaml / casting.yaml guardan RUTAS project-relative (D-044), no
// indices; la UI matchea por nombre de archivo contra las URLs servidas.
// Estaba copiada identica en Casting y Encuadres — la clase de duplicacion de
// VERDAD que produce des-sincronizaciones (la leccion D-080).

/** {clave: rutaElegida} + {clave: [urls]} -> {clave: indiceElegido} */
export function picksFromDisk(selections, urlsByKey) {
  const out = {};
  for (const [key, selPath] of Object.entries(selections || {})) {
    const urls = urlsByKey?.[key] || [];
    const filename = String(selPath).split(/[/\\]/).pop();
    const idx = urls.findIndex((url) => url.split("/").pop() === filename);
    if (idx >= 0) out[key] = idx;
  }
  return out;
}
