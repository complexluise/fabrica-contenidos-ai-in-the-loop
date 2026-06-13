# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

API-only multi-model **AI video generation pipeline**. Orchestrates Kling / Seedance / Veo (video) and Flux / nano-banana (keyframes) through **fal.ai**, with a Claude-vision Quality Gate, content-addressed caching, and **"AI-in-the-Loop" human checkpoints** (a human picks the character face and the keyframe among N candidates). Default style is LEGO; style is parametrizable.

Authoritative docs (read these before large changes): `PRD.md` (the what/for-whom + per-actor journeys), `ARCHITECTURE.md` (the how — layers + contracts), `ROADMAP.md` (index of sprints + acceptance criteria; closed work archived under `docs/roadmap/`), `docs/decisiones/` (numbered ADRs, max 10 per file — the *why* behind every choice). For authoring shots/prompts, `docs/oficio-video-ai.md` holds the sourced craft rules (i2v prompt dialect, brickfilm grammar, finishing recipe, takes economy) behind D-070..D-074.

## Commands

This project uses **`uv` exclusively** — never `pip`, `python -m venv`, or a bare `python`. Python is pinned to 3.12.

```bash
uv sync --extra apis --extra dev      # install: core + APIs (anthropic, fal-client) + pytest
                                       # add --extra vision for the dormant CLIP/aesthetic signals (heavy: torch)
uv run pytest                          # full test suite (asyncio_mode=auto, so async tests need no decorator)
uv run pytest tests/test_strategies.py # one file
uv run pytest tests/test_strategies.py::test_ensemble_picks_highest_score   # one test
uv run pipeline ...                    # run the CLI (entry point: pipeline.cli:app)
```

There is no linter/formatter configured. Tests are the only gate.

## Two execution modes (both go through the same layers)

**Autonomous** — one shot, AI decides everything:
```bash
uv run pipeline run <slug>                    # resolves projects/<slug>/project.yaml, uses cache
uv run pipeline run x --brief briefs/foo.yaml # smoke: ephemeral project under out/<stem>/ —
                                              # SAME pipeline as a project (cache, --profile), D-075
```

**Interactive (AI-in-the-Loop)** — staged, resumable, human picks at checkpoints:
```bash
uv run pipeline cast <slug> --n 4   →  pick-cast <slug> juan=2     # character face
uv run pipeline keyframes <slug> --n 4  →  pick <slug> s1=0 s2=3   # framing per scene
uv run pipeline animatic <slug>                                     # the film as stills, before video money
uv run pipeline render <slug>                                       # video from chosen keyframes
uv run pipeline takes <slug>  →  pick-take <slug> s2=<path>         # curate among N takes (D-074)
```

`uv run pipeline costs [--days N] [--project slug]` answers "how much have I spent" from the global ledger `out/telemetry.sqlite` (D-079; per-run `run_report.json` stays as the immutable manifest).
`cast`/`keyframes` generate N candidates and auto-open an **HTML contact sheet**; the human selects by index. Selections persist in the project (`selections.yaml` / `casting.yaml` / `pose_picks.yaml` / `take_picks.yaml`), so the flow is non-blocking and resumable — this matters because generation is slow (keyframe ~30-60s, video 1-3 min). Re-running already-generated work is **free** (cache).

## Architecture (the parts that span files)

10 layers decoupled by contracts, plus the interactive studio layer. Key flow:
```
L1 Ingest → L2 Classifier → L3 Keyframe → L4 Providers → L5 Orchestrator (router/cascade/ensemble)
→ L6 Quality Gate (Claude vision) → L7 Assembly → L8 Delivery        (L9 Telemetry, cross-cutting)
```

- **Contracts first (`contracts.py`).** `Scene` (pure narrative), `ShotJob` (the render job for ONE shot — what `Strategy`/`QualityGate` actually receive, D-075), `GenResult`, `GateReport` plus `Provider`/`QualityGate`/`Strategy` Protocols. Everything else depends on these, not on concrete classes. Pydantic v2. Do NOT add runtime/generation fields to `Scene` — they belong on `ShotJob`.

- **Provider abstraction (`providers/`).** All real video/image generation goes through `fal_client.AsyncClient` (submit + poll, `upload_file` for i2v `image_url`) — **never** raw httpx POST to fal. `build_provider` constructs from `config/providers.yaml`. `google_veo.py` needs `google-genai` and is **unvalidated against the real API**.

- **Strategies / orchestrator (`strategies/`).** Three strategies select cost-vs-quality: `router` (cheapest eligible), `cascade` (escalate tiers, accumulate cost, mark `needs_human` if all fail), `ensemble` (best-of-N in parallel, gate-ranked). `dispatch.py` reads `config/routing.yaml` to map scene **class** (`hero`→ensemble, `standard`→router, `volume`→cascade) to a strategy + provider list. Strategies are **tolerant of provider failure** (`asyncio.gather(..., return_exceptions=True)`) — one dead provider must not abort a scene.

- **Quality Gate (`gate/`).** Pluggable signals fused by weighted mean (`fusion.py`): `VLMSignal` (Claude multimodal vision) and `IdentitySignal` are active; `clip.py`/`aesthetic.py` are **dormant** behind the `[vision]` extra. The profile's `vlm_model` governs BOTH active signals (D-076); all Anthropic/Gemini calls go through `asyncio.to_thread` (sync clients must never block the event loop). Per "AI-in-the-Loop", the gate is a **ranker/assistant**, not an autonomous pass/fail — it orders the N candidates so the human picks faster. It is **soft by default** (`enforce: false` in routing.yaml): it scores and records but does not regenerate. Without `ANTHROPIC_API_KEY` the gate is permissive (never blocks).

- **Project / cache / runs model (`project.py`).** A project is `projects/<slug>/`. Caching is **content-addressed**: `cache_key(step, inputs)` = sha256[:16], cached at project level in `cache/`. Each run is an **immutable manifest** in `runs/<run_id>/`. A `.meta.json` sidecar preserves provenance + gate scores even on cache hits. Bumping a scene's `seed` is the "reroll" — it changes the cache key and regenerates **only that scene**.

- **Interactive studio (`studio.py` + `runner.py` + `contact_sheet.py`).** `studio.py` implements cast/keyframes/animatic/pick/render against project state. `runner.py::run_project` runs the **"camera acts" engine** (D-070, replacing D-060's universal interpolation — which, it turned out, never executed: **fal silently ignores unknown params**, and `end_image_url` doesn't exist on Kling 2.1 standard). Default per shot: i2v **from the chosen destination still** (the human's pick IS frame-0), prompt in the motion dialect (`shot.motion`, D-072 — camera instruction first, speed adverb, endpoint; never re-describe the scene), trim keeps the **head**. `shot.lands: true` opts into REAL interpolation (start pose → destination via `tail_image_url` on an `end_frame`-capable provider, e.g. `kling_pro`, 3× cost); trim keeps the **tail**. Start poses are generated **only for lands shots**. `shot.media: still` renders the shot as Ken Burns over the destination ($0 video); `shot.takes: N` generates N cached takes, gate-ranked, human overrides via `take_picks.yaml`. After concat+reframe, `finish.py` applies the style's **film stock** (grade → grain → loudnorm −14 LUFS, D-073, $0, best-effort). Per-shot try/except so **one failed shot does not abort the run**; it raises only if *every* shot fails. `pipeline animatic <slug>` shows the whole film as poses before any video money is spent. Captions (`post.py::burn_lower_third`) and background music (`assemble.py::concat_clips(..., music=...)`) are best-effort.

- **fal gotcha (the D-070 lesson, expensive to relearn).** fal endpoints **silently ignore unknown request params** — a misnamed param means you pay for a run that does something else, with no error. Before relying on any fal param, verify it exists on the EXACT endpoint variant (standard vs pro differ: end-frame is `tail_image_url`, pro-only). Provider capabilities in `providers.yaml` (e.g. `end_frame`) are the guard: `FalProvider` refuses to send an end image to an incapable model.

- **CLI as the public surface (`cli.py`).** Typer app with an `@app.callback()` so `run` is an explicit subcommand. **Skills and external agents target the CLI contract, not internal classes** (see D-023) — when changing a subcommand name, flag, or output format, update `skills/*/SKILL.md` and expect `tests/test_skills_contract.py` to catch drift. Internal `src/pipeline/` objects are freely refactorable; the CLI is versioned and defended.

## Configuration & secrets

- `config/providers.yaml` (models + per-second costs), `config/routing.yaml` (class→strategy, gate thresholds, `enforce`), `config/styles/<style>.yaml` (prompt template, `ref_model`).
- **`config.DEFAULT_PROFILE` (`fal-ultra-cheap`) is THE default everywhere** — CLI and server import it (D-076). Spending more than ultra-cheap is always an explicit human opt-in (`--profile` / `body.profile`); never silently default to `prod`.
- Secrets via `.env` (gitignored), read by `settings.py` (pydantic-settings v2). `FAL_KEY` is **required**; `ANTHROPIC_API_KEY` recommended (script decomposition, classifier, gate); `GOOGLE_API_KEY` optional (Veo).
- Generated images/videos are **not** committed.

## Conventions

- **TDD test-first** (red-green-refactor), but **only the critical core** — contracts, routing/strategies, gate fusion, telemetry, project/cache, studio. External APIs, ffmpeg, and prompts are validated by real smoke runs, **not** unit tests. Do not add broad test coverage beyond the core.
- **Prefer paid APIs over heavy local libraries** (no local whisper/torch/insightface in the default path) — this is why character consistency uses nano-banana + Claude vision, and CLIP/aesthetic stay dormant.
- **Sprint workflow:** work the whole sprint, then commit. Update `ROADMAP.md` (check AC) and `docs/decisiones/` before/as part of the work, not after.
- Windows/PowerShell host: avoid non-ASCII in console output (`->` not `→`; an earlier `→` print crashed on cp1252). ffmpeg must be on PATH.
- Git has no global identity configured here — commit with `git -c user.name="Luis" -c user.email="luis@sostaina.com"`.
