# skills/ — capa de discoverability para agentes ([D-023])

Cada skill es una **guía en markdown** que vuelve descubrible un flujo del pipeline
para un agente (opencode, claude code) o un humano. **No es código nuevo**: apunta a
los **subcomandos del CLI** (`pipeline …`), no a las clases internas de
`src/pipeline/`. El CLI es el contrato público versionado; el grafo de objetos es
interno y refactorizable.

## Batch actual

| Skill | Flujo | Checkpoint [D-021] |
|---|---|---|
| [`author-project`](author-project/SKILL.md) | brief → `project.yaml` | #1+#2 guion/shot list |
| [`bank-casting`](bank-casting/SKILL.md) | diseñar + fijar cara de personaje | #3 casting/look-dev |
| [`keyframe-best-of-n`](keyframe-best-of-n/SKILL.md) | N keyframes/escena → elegir → render | #4 keyframe |

Más skills se agregan por sprint cuando aparece la necesidad (p.ej.
`reordenar-cortes`, `brief-a-video`).

## Cómo authorar una skill nueva

1. Crea `skills/<nombre>/SKILL.md` con frontmatter (`name`, `description`).
2. Apunta a **subcomandos del CLI**, nunca a clases internas. Si te falta un comando,
   esa es una señal de que el CLI necesita crecer — no lo sortees llamando a internals.
3. Enlaza skills relacionadas con `[[nombre]]`.
4. **Declara un bloque smoke** al final (obligatorio, ver abajo).

## Smoke de contrato (obligatorio) — mata el drift silencioso

Una skill es prosa que codifica conocimiento del CLI; si un subcomando o flag cambia,
la skill queda obsoleta **sin que nada falle**. Es el mismo "Known drift" que el SPEC
de referencia documenta (`docs/SPEC-organic-illustration-pipeline.md` §10/F10).

Contramedida: cada `SKILL.md` termina con un bloque que lista las invocaciones
mínimas que menciona, en modo no-op (solo `--help`, sin gastar):

```text
<!-- smoke
pipeline keyframes --help
pipeline pick --help
pipeline render --help
-->
```

`tests/test_skills_contract.py` ejecuta esas invocaciones en CI. Si un subcomando
referenciado desaparece, el CLI sale != 0 y **el test grita** en vez de que la skill
se pudra callada. Córrelo con:

```bash
uv run --extra dev pytest tests/test_skills_contract.py -q
```
