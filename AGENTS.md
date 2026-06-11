# AGENTS.md

Guidance for agentic coding agents working in this repository. For deeper context (architecture, philosophy, sprint status) read [`CLAUDE.md`](./CLAUDE.md), [`SPEC.md`](./SPEC.md), and [`docs/decisiones/`](./docs/decisiones/) before large changes.

## Environment

- Python **3.12** (pinned via `.python-version`). Do not introduce newer-syntax requirements.
- Package manager: **`uv` exclusively**. Never `pip`, `python -m venv`, or a bare `python`.
- `ffmpeg` must be on `PATH` (assemble, audio, post, gate frames all shell out to it).
- Host is **Windows / PowerShell** with cp1252 default console. See "Console" below.
- Git has no global identity; commit with `git -c user.name="Luis" -c user.email="luis@sostaina.com"`.

## Build / install

```bash
uv sync --extra apis --extra dev      # core + API clients (anthropic, fal-client) + pytest
# Optional extras:
uv sync --extra vision                # CLIP/aesthetic gate signals (heavy: torch)
uv sync --extra studio                # FastAPI server
uv sync --extra edit                  # motion graphics (movis + numpy<2)
cp .env.example .env                  # then fill keys (FAL_KEY is required)
```

## Test commands

`asyncio_mode = "auto"` is set in `pyproject.toml`, so async tests **must not** carry `@pytest.mark.asyncio`. Tests are the only quality gate (no linter/formatter configured).

```bash
uv run pytest                                   # full suite
uv run pytest tests/test_strategies.py          # one file
uv run pytest tests/test_strategies.py::test_ensemble_picks_highest_score   # one test
uv run pytest -k "cascade"                      # substring filter
uv run pytest -x                                # stop on first failure
uv run pytest -q                                # quiet
```

When adding a new test, place it under `tests/test_<module>.py` and import from `pipeline.<module>` (the package is installed into the `uv` venv from `src/`).

## CLI

Entry point: `pipeline.__main__:main` -> `pipeline.cli:app` (Typer) or `pipeline.launcher` (GUI when run with no args).

```bash
uv run pipeline run <slug>                      # autonomous, one-shot
uv run pipeline run x --brief briefs/foo.yaml   # smoke, no project/cache
uv run pipeline cast <slug> --n 4               # generate N face candidates
uv run pipeline keyframes <slug> --n 4          # generate N keyframe candidates
uv run pipeline pick-cast <slug> juan=2         # human selects face
uv run pipeline pick <slug> s1=0 s2=3           # human selects keyframes
uv run pipeline render <slug>                   # render video from picks
```

## Code style

### Imports

- First line of every source file (except trivial re-export modules): `from __future__ import annotations`.
- Use **relative imports inside the package** (`from .runner import run_project`, `from ..config import Config`) — see `src/pipeline/strategies/dispatch.py:9` and `src/pipeline/runner.py:18`.
- Tests use **absolute imports** (`from pipeline.contracts import Scene`) — see `tests/conftest.py:5`.
- One import per line; group order: stdlib, third-party, local; one blank line between groups.
- Prefer `from x import Y` over `import x` when you only use one symbol.

### Formatting

- No formatter configured. Match surrounding code: 4-space indent, max line length ~100, no trailing whitespace, file ends with a single newline.
- Quote strings with double quotes (`"..."`) unless the string contains a double quote.
- **No comments unless they earn their keep.** Module/function docstrings: yes. Inline narration of obvious code: no.

### Types

- Pydantic **v2** for all data shapes that cross layer boundaries. See `src/pipeline/contracts.py:20`.
- Use `Field(default_factory=list)` for mutable defaults, `Field(gt=0)` for validated numerics.
- For Python keyword conflicts in YAML/JSON, use `Field(alias="class")` and `model_config = {"populate_by_name": True}` (see `Scene` in `contracts.py:71-82`).
- Prefer `Optional[X]` from `typing` (or `X | None` only when the file is already PEP 604 — the repo is mixed; match the file).
- Protocols in `contracts.py` (`Provider`, `QualityGate`, `Strategy`) are the public shape; concrete classes implement them.
- No `# type:` comments, no `.pyi` stubs, no mypy config.

### Naming

- `snake_case` for functions, variables, modules.
- `PascalCase` for Pydantic models and concrete classes (`Scene`, `GenResult`, `Cascade`).
- `UPPER_SNAKE` for module-level constants (`DEFAULT_VOICE_MODEL`, `SceneClass` literals).
- Spanish for **docstrings, user-facing error messages, log strings, and YAML keys/comments**; English for identifiers, type names, and the public CLI surface. The project is bilingual by design.

### Async

- `async def` everywhere a function does I/O. CPU-only helpers stay sync.
- Tolerate failure: `asyncio.gather(..., return_exceptions=True)` — one dead provider must never abort a scene (see `strategies/ensemble.py`). The runner's video phase is **sequential** (pixel-real ribbon, D-059): per-shot try/except; a failed shot cuts the chain but never aborts the run.
- `tests/` may use plain `async def test_…`; the `auto` mode picks it up.

### Error handling

- Raise the most specific builtin that fits: `ValueError` for bad input/format, `RuntimeError` for missing dependency / all-providers-failed / preconditions not met, `FileNotFoundError` for missing config files. See `src/pipeline/strategies/cascade.py:21`, `src/pipeline/gate/frames.py:18`, `src/pipeline/config.py:63`.
- Re-raise with cause when wrapping: `raise RuntimeError("…") from exc` (see `src/pipeline/author.py:148`).
- Pydantic models do their own validation; don't double-validate the same field.
- Best-effort features (captions in `post.py::burn_lower_third`, music in `assemble.py::concat_clips(..., music=...)`) swallow errors and log — they must not break the run.
- Per-scene `try/except` in `runner.py::run_project`; failures land in `run_report.json` via `telemetry.record_failure` and the run continues. Only raise if **every** scene fails (`runner.py:324`).

### Logging / printing

- `logger = logging.getLogger(__name__)` at module top for library code.
- CLI uses `rich.console.Console` (see `src/pipeline/cli.py:14`).
- **Console output is ASCII-only.** Use `->` not `→`, `==` not `≈`, etc. An earlier `→` print crashed on cp1252.
- `.md` files may use accents and Unicode freely.

### Architecture rules (non-negotiable)

- **Contracts first.** New layer integrations depend on `src/pipeline/contracts.py` (Pydantic models) and the `Protocol`s there, not on concrete classes.
- **All fal.ai calls go through `fal_client.AsyncClient`** — submit + poll, plus `upload_file` for i2v `image_url`. Never raw `httpx` POST to fal. See `src/pipeline/providers/`.
- **Strategies are tolerant of provider failure** (`asyncio.gather(..., return_exceptions=True)`). The three strategies live in `src/pipeline/strategies/`: `router`, `cascade`, `ensemble`. `dispatch.py` maps scene class -> strategy + provider list from `config/routing.yaml`.
- **Quality Gate is a ranker, not a veto** by default (`enforce: false` in `routing.yaml`). It scores and records; only enforces if `enforce: true`. Without `ANTHROPIC_API_KEY` it is permissive (never blocks). Signals: `VLMSignal`, `IdentitySignal` active; `clip.py`/`aesthetic.py` dormant behind `[vision]`.
- **Cache is content-addressed** (`cache_key(step, inputs) = sha256[:16]` in `project.py`), per-project under `projects/<slug>/cache/`. Bumping a scene's `seed` is the reroll knob — it changes the key and regenerates **only that scene**.
- **CLI is the public surface.** Skills and external agents target the CLI contract, not internal classes (D-023). When renaming a subcommand, flag, or output format, **update `skills/*/SKILL.md` in the same change** — `tests/test_skills_contract.py` catches drift.
- Internal `src/pipeline/` objects are freely refactorable; the CLI is versioned and defended.

### Testing philosophy

- TDD red-green-refactor, **but only for the critical core**: contracts, routing/strategies, gate fusion, telemetry, project/cache, studio. External APIs, ffmpeg, and prompts are validated by **real smoke runs**, not unit tests. Do not add broad coverage beyond this core (D-012).
- Use Fakes in tests, not mocks: `class FakeProvider` / `class FakeGate` patterns in `tests/test_strategies.py:20-48`. They expose the same attributes as the real class.
- Use `pytest.approx(...)` for float comparisons (`test_strategies.py:81`).

## Configuration

- `config/providers.yaml` — model registry and per-second costs.
- `config/routing.yaml` — class -> strategy, gate thresholds, `enforce` flag.
- `config/styles/<style>.yaml` — prompt template and `ref_model` per style (default: `lego`).
- Secrets in `.env` (gitignored), read by `src/pipeline/settings.py` (pydantic-settings v2). Never commit secrets.
- Generated images/videos are gitignored — do not add them.

## Sprint workflow

1. Open an issue for non-trivial changes; agree on the approach first.
2. Branch from `main`. Work the whole sprint, then commit.
3. Update `ROADMAP.md` (check AC boxes) and add an ADR under `docs/decisiones/` **as part of the work**, not after. ADRs are numbered, max 10 per file, format: *Contexto · Decisión · Consecuencias*.
4. Run `uv run pytest` and leave it green.
5. Open the PR. Fill the template (tests, ADR, skills). If you changed a CLI subcommand or flag, **update the matching `skills/*/SKILL.md`** in the same PR.

## PR checklist

- [ ] `uv run pytest` passes.
- [ ] If the CLI changed, `skills/*/SKILL.md` updated and `tests/test_skills_contract.py` still green.
- [ ] If a design decision was made, ADR added in `docs/decisiones/`.
- [ ] No `.env`, secrets, generated `*.mp4`/`*.png`, or `_internal/` artifacts in the diff.
- [ ] No non-ASCII characters in console output (`print`, `rich.console.print`, logger).
- [ ] Change respects the rule: **the human still decides.**
