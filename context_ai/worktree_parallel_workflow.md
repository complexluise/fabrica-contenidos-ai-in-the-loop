# Trabajo en paralelo con git worktree + opencode

> Cómo dejar a opencode trabajando en una rama mientras vos seguís en `main`
> (u otra) sin pisarse. Aplicado a este proyecto en Windows.

## Por qué

OpenCode opera sobre el **directorio** donde lo lanzás (cada carpeta = una
sesión propia). No tiene concepto interno de "rama del agente". Para
paralelizar hace falta dos working trees apuntando a la misma `.git`, cada uno
en su rama. Eso es exactamente lo que hace `git worktree`.

Alternativas descartadas:
- `git stash` + `git checkout`: no es paralelo, sólo uno trabaja a la vez.
- Clones múltiples: duplica `.git` (~50MB+), sincronizar requiere push/pull al
  remoto, ciclo más largo.
- `OPENCODE_EXPERIMENTAL_WORKSPACES`: feature experimental sin docs estables.

## Concepto

Un repo git tiene normalmente 1 working tree + 1 `.git/`. Con worktree:
**N working trees comparten el mismo `.git`**. Cada uno:
- Vive en su carpeta.
- Tiene su rama checkeada (la misma rama NO puede estar en dos worktrees).
- Comparte commits, branches, remotes, stash, hooks con los demás.
- Mantiene su propio working state (uncommitted, untracked).

## Setup paso a paso

### 1. Crear el worktree con rama nueva

Desde la raíz del repo (`video_gen_pipeline/`):

```bash
git worktree add ../video_gen_pipeline-ai -b feature/<nombre>
```

Esto crea `C:/Users/luise/Documents/Politica/video_gen_pipeline-ai/` checkeado
en `feature/<nombre>`. El repo original queda intacto en su rama.

Si la rama ya existe:
```bash
git worktree add ../video_gen_pipeline-ai feature/<nombre>
```

### 2. Replicar lo que NO está versionado

`git worktree` **no copia** archivos gitignored. En este proyecto:

| Archivo / dir | Acción |
|---|---|
| `.venv/` | Crear nuevo: `py -3.12 -m venv .venv && pip install -e ".[dev,apis]"` |
| `.env` | Copiar: `copy ..\video_gen_pipeline\.env .` |
| `out/`, `data/` | Vacíos, se llenan al correr |

Comando completo:
```bash
cd ../video_gen_pipeline-ai
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,apis]"
copy ..\video_gen_pipeline\.env .
pytest -q                  # debe dar 24 passed igual que main
```

### 3. Lanzar opencode en el worktree

Tres formas, todas equivalentes:

```bash
# A. Pasar la ruta como argumento
opencode C:/Users/luise/Documents/Politica/video_gen_pipeline-ai

# B. Entrar a la carpeta y lanzar
cd ../video_gen_pipeline-ai
opencode

# C. Headless + attach (sesiones largas, evita cold boot de MCP)
cd ../video_gen_pipeline-ai
opencode serve --port 4096
# en otra terminal:
opencode attach http://localhost:4096
```

OpenCode indexa sesiones por path → cada worktree tiene su propio historial.
Listar con `opencode session list`.

## Ciclo de trabajo

```
[Vos en main]                       [Opencode en feature/X]
 video_gen_pipeline/                 video_gen_pipeline-ai/
 - lees, comparas                    - edita, commitea
 - git pull origin main              - git push origin feature/X
                                     - abre PR cuando termina
```

Para ver el progreso del agente sin moverte de tu rama:
```bash
git fetch
git log feature/X --oneline
git diff main..feature/X
git diff main..feature/X -- src/pipeline/settings.py   # un archivo
git show feature/X:src/pipeline/settings.py            # ver contenido sin checkout
```

## Cleanup cuando el PR mergea

```bash
cd C:/Users/luise/Documents/Politica/video_gen_pipeline
git pull origin main                              # traer el merge
git worktree remove ../video_gen_pipeline-ai      # borra carpeta hermana
git branch -d feature/X                           # borra rama local
```

Si la carpeta tiene cambios sin commitear y querés forzar:
```bash
git worktree remove --force ../video_gen_pipeline-ai
```

## Estructura resultante en disco

```
C:/Users/luise/Documents/Politica/
├─ video_gen_pipeline/                  ← TU sesión (main)
│  ├─ .git/                             ← repo real, compartido
│  │  └─ worktrees/
│  │     └─ video_gen_pipeline-ai/      ← metadata del worktree
│  ├─ .venv/
│  ├─ .env
│  └─ src/, config/, tests/, ...
│
└─ video_gen_pipeline-ai/               ← OPENCODE (feature/X)
   ├─ .git                              ← archivo (no carpeta), apunta arriba
   ├─ .venv/                            ← venv propio (300 MB)
   ├─ .env                              ← copia
   └─ src/, config/, tests/, ...        ← mismos archivos, otra rama
```

## Gotchas

1. **Misma rama no puede estar en dos worktrees.** No podés checkear `main`
   en ambos. Workaround: ver con `git show main:path` o crear
   `main-readonly`.

2. **El `.git` del worktree es un archivo, no carpeta.** Es un text file con
   `gitdir: .../video_gen_pipeline/.git/worktrees/video_gen_pipeline-ai`.
   Normal. No lo borres.

3. **Hooks compartidos.** Viven en el `.git` original → se aplican en ambos
   worktrees. Bueno para consistencia.

4. **Stash es compartido.** `git stash` en un worktree aparece en el otro.
   Si confunde, etiquetá: `git stash push -m "ai-side: WIP"`.

5. **Sesiones de opencode separadas por path.** Cada worktree es un proyecto
   distinto para opencode → dos historiales independientes. Ver con
   `opencode session list`.

6. **IDEs.** Abrir ambos worktrees en VS Code al mismo tiempo duplica
   servidores LSP → más RAM, no crítico.

7. **Windows-specific.** `git worktree` funciona igual. Usar rutas absolutas
   o relativas con `/` o `\\` consistentes.

## Listar y diagnosticar worktrees

```bash
git worktree list                  # ver todos los worktrees activos
git worktree prune                 # limpiar metadata de worktrees borrados a mano
```

Salida típica de `list`:
```
C:/Users/luise/.../video_gen_pipeline      c59ebeb [main]
C:/Users/luise/.../video_gen_pipeline-ai   a1b2c3d [feature/llm-models-config]
```

## Múltiples worktrees simultáneos

Nada impide tener 3+ a la vez. Convención sugerida:
```
video_gen_pipeline/                ← main (vos)
video_gen_pipeline-ai/             ← feature actual del agente
video_gen_pipeline-review/         ← rama de un PR que estás revisando
video_gen_pipeline-hotfix/         ← bugfix urgente sin perder el contexto
```

Cada uno con su `.venv` o un solo venv compartido vía `VIRTUAL_ENV` env var
(más frágil, pero ahorra disco).

## Cuándo NO usar worktree

- **Cambios que tocan la config global del repo** (hooks, attributes, ignore):
  como se comparten, cambios en uno afectan al otro. Coordinar antes.
- **Experimentos con submódulos**: los submódulos en worktrees tienen edge
  cases. Este proyecto no usa submódulos, no aplica.
- **CI / GitHub Actions**: ellos clonan limpio, no necesitan worktree.

## Workflow concreto aplicado a este proyecto

Para el plan pendiente de "centralizar modelos Claude" (ver
`feedback_1_sprint_1.md` puntos 2 y siguientes):

```bash
# Desde video_gen_pipeline/ en main
git worktree add ../video_gen_pipeline-ai -b feature/llm-models-config

cd ../video_gen_pipeline-ai
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,apis]"
copy ..\video_gen_pipeline\.env .
pytest -q

opencode                           # pedirle que ejecute el plan

# Mientras tanto, vos en la otra terminal:
cd ../video_gen_pipeline
git fetch
git diff main..feature/llm-models-config   # revisar progreso

# Cuando opencode abra PR y mergees:
git pull origin main
git worktree remove ../video_gen_pipeline-ai
git branch -d feature/llm-models-config
```
