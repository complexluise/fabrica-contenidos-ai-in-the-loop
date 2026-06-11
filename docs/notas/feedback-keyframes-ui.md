# Feedback — Generación de planos y UI (diagnóstico de tensiones)

> Diagnóstico, no plan. No se proponen soluciones; se describen las tensiones
> observadas entre la implementación actual de la generación de planos
> (keyframes, casting, encadenado) y cómo se presenta en el Studio. La
> metodología es leer el código y la UI, identificar el desfasaje entre lo que
> el sistema hace y lo que la UI promete, y nombrarlo.

## Contexto

La "generación de planos" tiene tres sentidos coordinados que la UI
presenta en una sola pantalla (`Elegir` -> `Picker.svelte`):

1. **Casting**: N caras candidatas por personaje con `design:`, la elegida se
   vuelve referencia canónica de identidad.
2. **Encuadres (keyframes)**: N imágenes base por escena; la elegida se vuelve
   `init_image` del modelo image-to-video.
3. **Planos encadenados (D-048/A4)**: keyframes de los planos 2+ encadenados
   por i2i desde el ancla elegido. Es una **previsualización read-only**: el
   humano no elige entre ellos, el render no los usa como input durable.

Archivos clave:

- `src/pipeline/studio.py:194-456` — AI-in-the-Loop (`gen_keyframes`,
  `gen_keyframes_scene`, `preview_shot_keyframes`, `record_picks`).
- `src/pipeline/keyframe.py:56-185` — `KeyframeGenerator` (backends fal/google).
- `src/pipeline/contracts.py:112-161` — modelos `Shot` y `Scene`.
- `src/pipeline/config.py:62-109` — `ProfileConfig` (D-052) y `StoryboardConfig` (D-053).
- `src/pipeline/runner.py:82-244` — `_render_shot` (consume selecciones).
- `src/pipeline/server/app.py:405-435` — endpoints `/keyframes` y `/keyframes/{scene_id}`.
- `app/src/views/Picker.svelte:1-552` — UI de generación y elección.
- `app/src/views/Produccion.svelte:1-290` — UI de render.
- `app/src/lib/studio.svelte.js:30-36` — `GLOSARIO` declarado, no usado.

---

## Tensiones

### T1. Backend de imagen y perfil de video son dimensiones independientes sin contrato visual de combinación

**Evidencia.** D-053 las escinde formalmente: `StoryboardConfig` (creativo) vs
`ProfileConfig` (producción) en `config.py:62-109`. `Picker.svelte:33` declara
`genBackend = "fal"` como estado local; `Produccion.svelte:13` tiene
`concurrency` y un selector de `profile` separado. Las dos rutas viven en
`routing.yaml:16-43` (storyboard_backends) y `routing.yaml:45+` (profiles). El
toggle del Picker (`Picker.svelte:324-331`) no consulta ni muestra qué perfil
está activo en Producción. `storyboard_backend` persiste en `project.yaml`
(`Storyboard.svelte:215`), pero el perfil de producción no se persiste en el
proyecto; se pasa en cada `render`.

**Tensión.** El humano decide "imagen con Google, video con fal" sin que el
sistema registre ese par como un acoplamiento. La UI lo trata como dos
switches sueltos. La promesa "IA propone, vos elegís" se fragmenta en dos
dominios sin contrato visual de qué combinación eligió el humano para esta
entrega.

---

### T2. Los previews de planos 2+ se muestran como "cómo va a quedar" pero el render los regenera de otra forma

**Evidencia.** `preview_shot_keyframes` (`studio.py:335-397`) genera los
keyframes de los planos 2+ encadenados por i2i desde el ancla elegido y los
persiste en `shot_previews.yaml` con rutas absolutas y comentario explícito
"es una previsualizacion efimera". El server los expone en
`/api/projects/{slug}/candidates` (campo `shot_previews`) y la UI los consume
en `Picker.svelte:500-526`. El runner NO los lee (búsqueda de `shot_previews`
en `runner.py`: no aparece). En el render, los planos 2+ se derivan de
`shots[]` con la cadena i2i interna, no del YAML de previews.

**Tensión.** El humano ve un preview de coherencia de planos 2+ que NO va a
salir así en el render final. La UI presenta los previews al lado del ancla
elegido como si fueran "cómo va a quedar", cuando en realidad son una
simulación parcial. Tres artefactos distintos (keyframe elegido, previews
encadenados, render real) sin que la UI marque la diferencia.

---

### T3. "Regenerar" es acumulativo y opaco; no hay forma de descartar keyframes desde la UI

**Evidencia.** `gen_keyframes` (`studio.py:194-269`) reensambla
`results[s_idx]` desde lo que retornó el `gather`; si el humano lo corre
nuevamente, pisa `candidates.yaml` por escena con los nuevos resultados (no
mergea entre escenas). `gen_keyframes_scene` (`studio.py:272-332`) sí mergea
con `seed_offset = len(existing)` (`studio.py:304`). El endpoint
`POST /api/projects/{slug}/keyframes` (`app.py:405-417`) no documenta que
sobrescribe. No existe endpoint para borrar cache de keyframes ni para borrar
candidatos de una sola escena. `cache_lookup` (`studio.py:224`) hace cache
content-addressed; regenerar con la misma `(styled, seed)` no gasta, pero
cambiar `n` de 4 a 2 deja huérfanos los índices 2,3 en `candidates.yaml`.

**Tensión.** "Regenerar" se siente destructivo pero en realidad acumula. El
humano no puede decir "dejame solo 3, descartá el 4". El estado latente de "lo
que vio antes" sobrevive en `candidates.yaml` aunque la UI muestre N=2. La
decisión de cuántos keyframes mantener por escena no tiene punto de control
explícito.

---

### T4. La granularidad de control (global / escena / plano) no está marcada y el foco no está jerarquizado

**Evidencia.** `Picker.svelte:420-463` ubica el panel "Para la IA" DENTRO de
cada escena, compitiendo por atención con la lighttable de candidatos
(`Picker.svelte:488-497`). `compilePrompt` (`Picker.svelte:165-184`) recompila
el prompt DESPUÉS de que la IA ya generó; el humano debe regenerar keyframes
para ver el efecto. No hay loop automatizado de "compilás prompt -> regenerás
keyframes". El badge `prompt_stale` (`Picker.svelte:425-433`) se deriva de
`prompt_src_hash`; la única acción masiva es "Compilar prompts
desactualizados" (`Picker.svelte:365-368`). `genBackend` y `n` son globales al
proyecto (`Picker.svelte:33-34`), pero `prompt_tweak` es por escena
(`Picker.svelte:125-140`) y los `framings` son por plano dentro de la escena
(`Picker.svelte:446-452`).

**Tensión.** La UI tiene tres niveles de granularidad (global / escena /
plano) sin marcarlo. El humano no sabe si el tweak que tipeó se va a aplicar a
la próxima generación de esa escena, a todas las escenas, o si quedó como
prompt manual permanente. La promesa D-046 ("la IA propone, vos firmás") se
rompe en el medio: hay un parche manual no formalizado.

---

### T5. "Guardar selección" no es idempotente respecto al estado firmado y a la realidad del disco

**Evidencia.** `record_picks` (`studio.py:434-456`) escribe `selections.yaml`
cada vez. `add_candidate_upload` (`studio.py:400-424`) modifica
`candidates.yaml` sin invalidar `selections.yaml`: si el humano sube una
imagen y NO la selecciona, queda como candidato huérfano. `prune_selections`
(`studio.py:459-473`) descarta selecciones cuyo `scene_id` no existe (D-022),
pero NO descarta selecciones cuyo `path` ya no existe en disco (borrado
manual, cache miss, mover de máquina). En `Picker.svelte:280-292`, `savePicks`
sobreescribe `kfPicks` y `castPicks` desde los estados locales pre-poblados de
disco (`Picker.svelte:70-86`). Si el humano navega a otra pestaña del navegador
y vuelve, no hay re-sync.

**Tensión.** "Guardar" parece una acción simple pero implica una
reconciliación entre `kfPicks` local, `selections.yaml` en disco, y la realidad
de qué archivos existen. La UI no avisa cuando una selección previa apunta a
un archivo que ya no está. El humano descubre la rotura al renderizar.

---

### T6. La concurrencia existe en backend pero la UI la expone solo para Producción, no para Picker

**Evidencia.** `cli.py:222` define `concurrency: int = 5` para `keyframes`.
`app.py:406` recibe `concurrency: int = 5` en `POST /api/projects/{slug}/keyframes`.
`Picker.svelte:103-116` no envía `concurrency`; usa el default. `Produccion.svelte:13`
declara `concurrency = 3` con selector 1/3/5 (`Produccion.svelte:156-158`). El
server no valida que `concurrency` no exceda límites de rate del provider.

**Tensión.** Hay un dial en Producción que dice "velocidad" pero no hay dial
equivalente para "velocidad de generación de keyframes". Generar 4 keyframes ×
12 escenas = 48 requests en silencio a 5 simultáneos (≈10 lotes), sin que el
humano lo sepa. La decisión de costo/tiempo está oculta. Si el provider
rate-limita, los timeouts aparecen como `done: failed` en el SSE.

---

### T7. El foco guiado puede mentir si se firma con defaults o si el cache de settings queda obsoleto

**Evidencia.** `compute_stage` (`state.py:85-105`) decide en base a
`storyboard.signed` + artefactos presentes. El Studio avanza a "Elegir" cuando
hay storyboard firmado, pero el humano puede haber firmado con
`visual_intensity` en null, sin `shots[]` rellenos, o con una `class_` que no
existe en `routing.yaml.profiles`. `dispatch.py:21-23` cae a `standard` si la
clase no está, sin avisar. El humano firma con `class_: "epic"`, el runner la
trata como `standard`, y nunca se entera. `app.py:613` cachea `get_settings()`;
editar `.env` a mano no actualiza el server hasta reinicio.
`Picker.svelte:336-352` bloquea "Generar encuadres" si `castNeeded && !castReady`,
pero si `casting.yaml` tiene una cara y el server reinició, el cache de
`status` puede mostrar un estado obsoleto por unos segundos.

**Tensión.** La UI vende "foco guiado, no te perdés", pero el foco se calcula
en base a firmas que pueden ser por defecto o falsos positivos (firmar sin
completar). El humano avanza confiado por una espina que no detecta
configuraciones inválidas hasta el render.

---

### T8. `GLOSARIO` existe como contrato de UX pero no se renderiza

**Evidencia.** `studio.svelte.js:30-36` define `GLOSARIO` con `plano`,
`keyframe`, `casting`, etc. Búsqueda exhaustiva en `app/src/`: `GLOSARIO`
declarado una vez, referenciado cero veces fuera de su declaración.
`Picker.svelte:319-321` usa los términos en copy suelto ("Casting = la cara
del personaje", "Encuadres = la imagen base"), no en un sistema de tooltips.
AGENTS.md promueve español para user-facing, pero el glosario es código
muerto.

**Tensión.** Hay una decisión de diseño incompleta. El bilingüismo del
proyecto (español/inglés) y la jerga técnica coexisten sin un patrón de
mediación para el humano no técnico. Resultado: copy inconsistente; "ancla",
"plano 1", "encuadre", "keyframe", "shot" se usan como sinónimos sin
glosario.

---

### T9. `shot_previews.yaml` es read-only persistente pero no se actualiza con cambios del ancla

**Evidencia.** `preview_shot_keyframes` (`studio.py:335-397`) escribe
`shot_previews.yaml` con rutas absolutas y comentario explícito de que es
efímero. La UI lo consume en `Picker.svelte:500-526`. El runner NO lo lee. No
hay endpoint para borrar `shot_previews.yaml`. Si el humano regenera el ancla
(cambia `kfPicks[scene]`), `shot_previews.yaml` queda con el ancla VIEJO hasta
que el humano regenera manualmente. El botón "Regenerar planos"
(`Picker.svelte:506`) usa la heurística `previews.length > 1` para activar
`force=true`, no deriva del cambio real del ancla.

**Tensión.** Los previews son read-only pero persistentes, no se actualizan
automáticamente, y la UI los muestra al lado del ancla. El humano ve
inconsistencia temporal: "elegí este ancla, pero los planos todavía muestran
el anterior". El flag de "regenerar" es heurístico, no deriva del cambio real.

---

### T10. Casting y encuadres son hermanos asimétricos; regenerar uno no invalida al otro

**Evidencia.** `Picker.svelte:383-405` (Casting) y `407-530` (Encuadres)
tienen la misma estructura de lighttable, pero:
- Casting: las refs se inyectan automáticamente a TODOS los keyframes que
  referencian al personaje (`keyframe.py:_submit_fal` usa `ref_model` con las
  caras del casting).
- Encuadres: son la imagen BASE; el render produce video encima.

Si el humano regenera casting sin re-elegir caras, los índices viejos en
`casting.yaml` quedan apuntando a archivos que pueden o no existir.
`record_cast_picks` (`studio.py:150-169`) escribe `casting.yaml`
(project-relative, D-044); `record_picks` (`studio.py:434-456`) escribe
`selections.yaml` (project-relative). Dos archivos, misma forma conceptual,
dos lifecycles.

**Tensión.** El humano los vive como "elige A, elige B" en la misma pantalla,
pero invalidar uno no invalida al otro. Regenerar caras (porque la nueva cara
es mejor) NO obliga a regenerar keyframes (que ya usaron la cara vieja como
ref), y la UI no avisa que los keyframes existentes se generaron con
identidad obsoleta. La asimetría está silenciada.

---

### T11. La imagen subida por el humano entra al pool sin marcar su origen

**Evidencia.** `add_candidate_upload` (`studio.py:400-424`) guarda en
`cache/keyframes/upload_<hash>.png` y lo concatena a
`candidates.yaml[scene_id]` con la misma estructura que un generado.
`Picker.svelte:144-162` lo envía en base64 y la UI lo muestra en la lighttable
igual que los demás. No hay campo `source: "ia" | "upload"` en el manifest; el
origen se infiere por el prefijo `upload_` en el nombre del archivo, pero ese
prefijo NO se preserva en la ruta project-relative de `selections.yaml` (se
relativiza a `cache/keyframes/<hash>.png`).

**Tensión.** El humano sube su propia foto, la selecciona, y al renderizar el
runner la usa como `init_image` (`runner.py:112-115`). La UI no le recuerda al
humano "esto es TU foto, no la IA". Cuando el humano ve el preview del video
final, no puede distinguir qué escenas usaron material suyo vs material
generado.

---

### T12. Prompt stale + keyframe elegido verde = dos snapshots desalineados

**Evidencia.** `PUT /api/projects/{slug}` con `sign: true` (`app.py:210`) firma
`storyboard.signed`. `prune_selections` (`app.py:240-245`) descarta
selecciones cuyo `scene_id` ya no existe. Si el humano edita el `prompt` o el
`framing` de un shot DESPUÉS de elegir keyframes, `prompt_src_hash` cambia,
`prompt_stale = true` (badge en `Picker.svelte:425-433`), pero los keyframes en
`selections.yaml` SIGUEN siendo los mismos archivos en disco
(`cache/keyframes/<hash>.png`). El render usa el ancla (keyframe elegido)
como `init_image`, pero el prompt para el VIDEO es el prompt recompilado
(`prompt_compile.py:compose_video_prompt`). Hay un desfasaje: el keyframe
representa el prompt VIEJO, el video representa el prompt NUEVO.

**Tensión.** El humano firma, elige, edita la narrativa, vuelve a firmar. El
sistema le muestra "⚠ desactualizado" en el prompt, pero la elección del
keyframe sigue verde. La decisión "qué ve el humano en el render final" se
compone de dos snapshots desalineados. La UI trata el prompt stale como
"advertir, no invalidar" — coherente con D-046 — pero no resuelve la
contradicción: el keyframe elegido fue generado con `framing_v1`, el video se
genera con `framing_v2`.

---

### T13. `shots: []` se traduce a 1 plano implícito sin avisar al humano

**Evidencia.** `project.py:289-295` define `effective_shots(scene)`: si
`shots` está vacío, devuelve `[Shot(...defaults...)]`. En `Storyboard.svelte:216-228`,
el PUT body hace `s.shots.map(...)`. Si el frontend envía `shots: []`, la
escena queda guardada con `shots=[]`, y el sistema "fabrica" un plano. No hay
validación server-side que avise: "estás por firmar una escena con 0 planos,
¿querés que el sistema sintetice uno o preferís definirlo?". El humano edita
duración, intensidad visual, pero no ve un warning de "esta escena no tiene
planos definidos".

**Tensión.** El sistema "esconde" la falta de definición detrás de un default.
La UI no señala la incompletitud. El humano puede firmar un plan con N
escenas donde M tienen planos vacíos, y descubrirlo solo en el render
(cuando los planos 2+ no encadenan porque no hay spec).

---

### T14. La selección puede apuntar a archivo borrado y la UI no reconcilia al cargar

**Evidencia.** `runner.py:112-115` lee la selección de disco; si el archivo no
existe (cache limpiada, proyecto movido de máquina, `candidates.yaml` apunta a
un `cache/keyframes/<hash>.png` purgado), el `init_image` falla.
`record_picks` (`studio.py:451`) persiste la ruta project-relative
(`cache/keyframes/<hash>.png`), portable entre máquinas pero NO entre
limpiezas de cache. No hay endpoint para "verificar integridad de
selecciones". En `Picker.svelte:42-90`, `load()` pre-puebla `kfPicks` desde
disco, buscando por nombre de archivo. Si el archivo no está, `idx = -1`, y
la escena queda SIN selección efectiva pero con la entrada en
`selections.yaml` apuntando al fantasma.

**Tensión.** El humano abre el proyecto, ve que tiene todo elegido (badges
"elegido · 2" en cada escena), pero al renderizar varios fallan en silencio o
con error genérico. La UI no le dice "3 de tus selecciones apuntan a archivos
borrados". El estado del disco no se reconcilia con el estado de la UI al
cargar.

---

### T15. No hay contador de costo durante la generación; el humano no sabe cuánto va a gastar

**Evidencia.** `StoryboardConfig.est_cost_per_image_usd = 0.003` (fal) / `0.002`
(google) (`config.py:93`). `ProfileConfig.est_cost_per_scene_usd = 0.05`
(default) (`config.py:69`). `gen_keyframes` no muestra costo; `runJob` solo
streamea `logger.info` por SSE. `Picker.svelte:33-35` no acumula un running
total. "Regenerar casting" o "Generar encuadres" no avisa "esto costará aprox
$X". El humano puede regenerar 4 veces el mismo set de encuadres sin saber
que está pagando 4×N.

**Tensión.** "La IA propone" sin costo visible puede generar comportamiento
de "pruebo y descarto" sin conciencia presupuestaria. La UI no expone un
dial de costo-vs-calidad. D-012 dice que el Quality Gate puntúa pero no
enforce; el costo es una restricción del proveedor (fal cobra por request),
no del gate. El humano descubre el gasto en la factura de fal.ai al final del
mes.

---

## Lo que NO está cubierto (límites del diagnóstico)

- No se evalúa si D-051/D-052/D-053 están bien decididos arquitectónicamente;
  solo se describe cómo su implementación en la UI genera las tensiones.
- No se proponen fixes, refactors ni rediseños.
- No se entra en las tensiones del Quality Gate (D-012), del runner
  end-to-end, ni de la lógica de routing/strategies — son ortogonales al flujo
  de keyframes/UI.
- No se evalúa performance ni rate limits de fal/google más allá de lo que la
  UI expone u oculta.

## Caminos para profundizar (no implementación)

Si se quiere abrir alguna dimensión antes de cerrar:

- **Costo y rate limits**: cómo se compara `est_cost_per_image_usd` vs
  realidad de fal; dónde está la fuga.
- **Ciclo de vida de artefactos** (`candidates.yaml`, `selections.yaml`,
  `casting.yaml`, `shot_previews.yaml`, `storyboard.signed`): quién los lee,
  quién los escribe, qué pasa si dos los modifican.
- **Modelo de "firma"** (D-022, D-033): qué es firmable, qué consecuencias
  trae, qué no.
- **Errores silenciosos** en `runner.py:_render_shot`: cuántos `try/except`
  swallow hay, qué se pierde.
- **Estado de red y SSE**: qué pasa si el server se cae a mitad de un job,
  qué ve el humano.
