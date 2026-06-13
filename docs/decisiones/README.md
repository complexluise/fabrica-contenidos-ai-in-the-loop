# Registro de Decisiones (ADR)

Decisiones de arquitectura/tecnología del pipeline, **numeradas** y con estado, para poder
discutir cada una y rastrear **qué cambió**. Máximo **10 decisiones por archivo**; la numeración
es continua entre archivos.

- Formato de cada decisión: Contexto · Decisión · Consecuencias · Cambios (si se revisó).
- Estados: **Vigente** · **Revisada** (sigue válida pero se ajustó) · **Reemplazada por D-XXX** · **Diferida**.
- La arquitectura y los contratos viven en [`ARCHITECTURE.md`](../../ARCHITECTURE.md); el *qué/para-quién* en [`PRD.md`](../../PRD.md); aquí solo el *por qué*.

## Índice

### [0001-0010.md](0001-0010.md)
| # | Decisión | Estado |
|---|---|---|
| D-001 | Orquestación en Python + asyncio (no ComfyUI/n8n) | Vigente |
| D-002 | Acceso a modelos vía agregador fal.ai (+ directos a volumen) | Vigente |
| D-003 | El LoRA de estilo vive en la imagen (Flux), no en el video | Vigente |
| D-004 | Modelos de video por tier: Kling / Seedance / Veo | Revisada |
| D-005 | Clasificador de escenas híbrido (reglas + Claude) | Vigente |
| D-006 | Estrategias Router / Cascade / Ensemble (híbrido por YAML) | Vigente |
| D-007 | Quality Gate basado en VLM-judge (Claude visión) | Revisada |
| D-008 | Ensamblaje y entrega con ffmpeg | Vigente |
| D-009 | Estado/cola: SQLite + asyncio ahora; Temporal/Postgres a escala | Vigente |
| D-010 | Gestión de Python: solo uv | Vigente |

### [0011-0020.md](0011-0020.md)
| # | Decisión | Estado |
|---|---|---|
| D-011 | Secretos con pydantic-settings (.env) | Vigente |
| D-012 | TDD selectivo, test-first del core crítico | Vigente |
| D-013 | Modelo de proyecto: spec + caché content-addressed + runs-manifiesto | Vigente |
| D-014 | Granularidad de iteración = escena; seed determinista + reroll | Revisada |
| D-015 | Caché a nivel proyecto + procedencia con sidecar | Vigente |
| D-016 | Quality Gate "duro": señales enchufables + fusión ponderada | Vigente |
| D-017 | Preferir APIs sobre librerías pesadas (CLIP/aesthetic dormidas) | Vigente |
| D-018 | Gate suave por defecto (toggle `enforce`) | Vigente |
| D-019 | Consistencia de personaje API-first (no insightface) | Vigente |
| D-020 | Model IDs validados contra fal (no especulativos) | Vigente |

### [0021-0030.md](0021-0030.md)
| # | Decisión | Estado |
|---|---|---|
| D-021 | "AI in the Loop": diseñar primero el flujo humano (checkpoints) | Vigente |
| D-022 | Interacción: subcomandos con estado + hoja de contactos (B+C+E) | Revisada |
| D-023 | Skills como capa de discoverability para agentes (apuntan al CLI) | Vigente |
| D-024 | Voz en off por escena con ElevenLabs (TTS), opcional | Vigente |
| D-025 | `render`/selección admiten el artefacto directo por flag | Vigente |
| D-026 | Artefactos con nombre semántico legible (hash como verdad del caché) | Vigente |
| D-027 | Logging detallado (L9): logging + RichHandler a stderr + run.log por corrida | Vigente |
| D-028 | La escena compone planos (`shots`); plano 1 = keyframe, los demás autogenerados | Vigente |
| D-029 | Export bundle para edición humana (`pipeline export`): media/frames/guion/srt | Vigente |
| D-030 | `guion.md` completo (script) + conversor md→docx (frontmatter, best-effort) | Vigente |

### [0031-0040.md](0031-0040.md)
| # | Decisión | Estado |
|---|---|---|
| D-031 | Studio local: app web local (FastAPI + Svelte, sin auth) sobre el pipeline | Vigente |
| D-032 | Estado del bucle derivado del disco (fuente única server/UI) | Vigente |
| D-033 | Entrada desde la app: importar texto -> storyboard editable | Vigente |
| D-034 | Diseño sonoro: SFX + ambiente vía video-to-audio (MMAudio), nativo premium | Vigente |
| D-035 | UX del bucle: Configuración fuera del bucle + firma explícita del plan | Vigente |
| D-036 | Biblioteca global de assets reusables (personajes/símbolos/lugares) | Vigente (en diseño) |
| D-037 | Frame por plano (auto) + cortes cortos (refina D-028) | Vigente (en diseño) |
| D-038 | Perfiles de calidad `proto`/`prod` seleccionables desde el CLI | Vigente |
| D-039 | Escenas en paralelo: semáforo de concurrencia en el runner | Vigente |
| D-040 | Inputs: foco rojo (gesto humano) + textarea base + texturas por nivel editorial | Vigente |

### [0041-0050.md](0041-0050.md)
| # | Decisión | Estado |
|---|---|---|
| D-041 | Ojos semánticos: `pipeline describe` (Haiku ve y evalúa cada plano) | Vigente |
| D-042 | Edición autónoma mixta: movis (CLI) + mcp-video (MCP), sin EDL | Vigente |
| D-043 | Selección explícita de proveedor: `proto_veo` como perfil propio (no fallback) | Vigente |
| D-044 | Metadata `_meta` en perfiles + `/api/profiles` endpoint (UI dinámica) | Vigente |
| D-045 | Storyboard centrado en la historia (humano): prompts se desplazan a Elegir | Vigente |
| D-046 | Prompt derivado de la narrativa (compilable + sincronizable) | Vigente |
| D-047 | El plano como artefacto audiovisual: gramática de cámara + estructura de Block | Vigente |
| D-048 | Coherencia de planos (keyframe ≠ video, encadenado) + flujo guiado por foco | Vigente |
| D-049 | Casting como artefacto de personaje | Vigente |
| D-050 | Convención de idioma: usuario en español, IA en inglés | Vigente |

### [0051-0060.md](0051-0060.md)
| # | Decisión | Estado |
|---|---|---|
| D-051 | Backend de keyframe por Google (Gemini) + toggle fal/Google + acciones masivas | Vigente |
| D-052 | Perfiles multi-rol (video + keyframe + gate VLM + LLM) + visibilidad de costos | Revisada por D-053 |
| D-053 | Split storyboard backend / render profile: dos configs para dos fases | Vigente |
| D-054 | Endurecimiento post-review Sprint 1: i2v exigido + telemetría con cierre garantizado + concat robusto | Vigente |
| D-055 | Endurecimiento keyframes/UI: integridad de artefactos + avisos no bloqueantes + costo visible | Vigente |
| D-056 | `render()` valida casting además de selections (cierra el hueco simétrico de integridad) | Vigente |
| D-057 | Cerrar el ciclo guion→spec: voz por `voiceover`, `needs_audio` no abusado, advisories + guard de routing | Vigente |
| D-058 | Backend de voz seleccionable (ElevenLabs prod / Kokoro proto) como eje independiente persistido | Vigente |
| D-059 | Cinta de planos pixel-real: el keyframe es el DESTINO del plano, no el frame-0 (revisa D-039/D-048) | Revisada por D-060 |
| D-060 | Animatic de poses frontera: el film en stills curables; video = intercalado paralelo (revisa D-059) | Revisada por D-070 |

### [0061-0070.md](0061-0070.md)
| # | Decisión | Estado |
|---|---|---|
| D-061 | El Studio en etapas: "Elegir" se separa en Casting / Encuadres / Animatic | Vigente |
| D-062 | Gramática de cobertura: el oficio entra al canal de avisos (y la plata se nombra) | Vigente |
| D-063 | Palancas de calidad: el preset de imagen pisa al estilo + poses elegibles (best-of-N) | Vigente |
| D-064 | Notas de dirección corte #3: subtítulos IG + coherencia extrema por ancla + keys posicionales | Vigente |
| D-065 | Voz por PLANO: dos hablantes conviven en una escena (plano → escena → proyecto → motor) | Vigente |
| D-066 | Timeouts duros en todo fal + fallos best-effort visibles (nada cuelga, nada muere mudo) | Vigente |
| D-067 | Ingeniería de contexto: biblia del mundo + estilo al video + referencias con nombre | Vigente |
| D-068 | La edición entra al flujo: cobertura conservada + ritmo de edición + música por defecto (corrige D-062) | Vigente |
| D-069 | Juicio del movimiento y corte humano: gate multi-frame + acción libre + export como sala de edición | Revisada por D-070 (is_anchored) |
| D-070 | El motor fantasma: end-frame real (`kling_pro`/`tail_image_url`) + "la cámara actúa" (`lands`) | Vigente |

### [0071-0080.md](0071-0080.md)
| # | Decisión | Estado |
|---|---|---|
| D-071 | 9:16 de punta a punta: el formato del spec viaja a imagen y video (la cadena estaba rota) | Vigente |
| D-072 | El dialecto de movimiento: `shot.motion`, prompt de video motion-only, negative de tiempo, cfg | Vigente |
| D-073 | La capa de finishing: el "film stock" en ffmpeg (grade+grano+loudnorm), $0/corrida | Vigente |
| D-074 | La economía de tomas: N takes + ranking del gate + pick humano + stills Ken Burns | Vigente |
| D-075 | ShotJob: el contrato del plano + un solo pipeline | Vigente |
| D-076 | Disciplina de costo: un default, gate async, modelo por perfil, contabilidad honesta | Vigente |
| D-077 | Fronteras honestas: nombres públicos, disciplina de cache y guard de slug | Vigente |
| D-078 | El recorrido de ejecución: la voz no estira el film y los checkpoints ven lo que compra el render | Vigente |
| D-079 | El libro mayor de costos: telemetría global, no por run | Vigente |
| D-080 | La superficie se sincroniza con el motor: muere "elegir", mueren las poses fantasma | Vigente |

### [0081-0090.md](0081-0090.md)
| # | Decisión | Estado |
|---|---|---|
| D-081 | El frontend se vuelve Svelte de verdad: mutación directa, remount por key, verdad compartida | Vigente |
| D-082 | Hardening post-auditoría: contrato UI↔server honesto, sin doble gasto, firma no se borra en silencio | Vigente |
| D-083 | El dashboard de jobs: un dock siempre visible, no una pantalla aparte | Vigente |
| D-084 | El casting hereda el patrón fluido de los encuadres (variantes, ajuste, subir, descartar) | Vigente |
| D-085 | El casting completa el patrón: el prompt del personaje, visible y editable | Vigente |
| D-086 | El Storyboard es el centro: las mesas lo nutren, todo se valida ahí | Vigente |
| D-087 | El player como proyección del guion (en el Storyboard) + el sidebar como árbol | Vigente |
| D-088 | Arquitectura de documentos: una pregunta por archivo, índice que no miente | Vigente |
| D-089 | Orquestación multi-agente: PO humano + architect / coder / verifier | Vigente |
| D-090 | Los jobs ganan historia: persistencia en SQLite (event-source liviano), barrido al boot | Vigente |
