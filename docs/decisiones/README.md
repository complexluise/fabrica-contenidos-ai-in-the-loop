# Registro de Decisiones (ADR)

Decisiones de arquitectura/tecnología del pipeline, **numeradas** y con estado, para poder
discutir cada una y rastrear **qué cambió**. Máximo **10 decisiones por archivo**; la numeración
es continua entre archivos.

- Formato de cada decisión: Contexto · Decisión · Consecuencias · Cambios (si se revisó).
- Estados: **Vigente** · **Revisada** (sigue válida pero se ajustó) · **Reemplazada por D-XXX** · **Diferida**.
- La arquitectura y los contratos viven en [`SPEC.md`](../../SPEC.md); aquí solo el *por qué*.

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
