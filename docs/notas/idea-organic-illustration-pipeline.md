# SPEC — Organic Illustration Pipeline

> A reusable pattern for producing narrative-driven, palette-locked,
> transparent-background illustrations at scale, by separating the
> **authored catalog** from the **deterministic renderer**.

| Field    | Value                                                   |
| -------- | ------------------------------------------------------- |
| Status   | Draft                                                   |
| Version  | 0.1.0                                                   |
| Audience | Agents (opencode, claude code) and humans authoring prompts |
| Language | English                                                 |
| License  | Same as parent repo                                     |

## 1. Context

Campaign, civic, and editorial projects often need a large set of
**bespoke, on-brand illustrations** that no stock library can supply.
Hand-illustrating them is expensive; pure prompt-to-image without
constraints produces visual drift and inconsistent silhouettes.

This SPEC defines a three-layer pattern that addresses both:

1. A **catalog** of structured prompt entries, authored by a human
   or an LLM agent, one per asset.
2. A **renderer** that takes a catalog entry, composes a deterministic
   prompt, calls a generative image model, post-processes the result,
   and writes a predictable output file.
3. A **consumer** that maps stable asset ids to rendered URLs in the
   host application (Storybook, app, slides, web pages).

The catalog is the only creative surface. The renderer and the
consumer are mechanical. The system is designed so that:

- An agent can author new catalog entries by following the
  **Authoring rules** in §6.
- A new project can fork the system by following the
  **Adaptation guide** in §9.
- Visual drift is minimised because every prompt is prefixed by a
  shared **style template** (§5) and constrained to a token palette.

The reference implementation lives in
`carrousel_CTeI/scripts/generate_assets.py`; see §10 for known drift
between this documentation and that script.

## 2. Goals and Non-Goals

### 2.1 Goals

The system MUST guarantee that:

- **G1 — Stable identity.** Each asset has a stable `id` that does
  not change across regenerations. The output filename is
  `<raster_dir>/<id>.png`.
- **G2 — Deterministic composition.** Given the same `id` and the
  same prompt, the renderer MUST produce the same composed full
  prompt (style template + entry prompt).
- **G3 — Palette conformance.** The style template and every
  catalog entry MUST reference only colors from the project's
  declared palette tokens. No hex values may appear outside the
  style template's palette block.
- **G4 — Transparency.** Every output PNG MUST have an alpha
  channel and the background MUST be fully transparent.
- **G5 — No embedded text.** No text, numbers, watermarks, or
  borders may appear in the rendered image. This is enforced by
  the prompt, not by post-processing.
- **G6 — Idempotent regeneration.** Running the renderer twice with
  the same catalog MUST overwrite the same files. There MUST be
  no side effects outside `<raster_dir>`.
- **G7 — Bounded failure.** A failure on one entry MUST NOT abort
  a batch. Each entry's outcome MUST be logged.

### 2.2 Non-Goals

The system does NOT aim to:

- Produce photorealistic, gradient-heavy, or shaded imagery.
- Replace the need for human curation of the catalog
  (auto-generation of the catalog is out of scope).
- Guarantee byte-identical output across different model versions
  or API backends.
- Detect or fix copyright concerns in model outputs.
- Render text overlays, callouts, or any layer that contains
  readable characters.

## 3. Architecture

The system has three layers, executed left to right at build time:

```
   ┌──────────────────────────────────────────────────────────┐
   │  1. CATALOG  (authored by human / agent)                 │
   │  ─────────────────────────────────────                   │
   │  • One file: catalog.{yaml,json,ts}                     │
   │  • Shape: id → PromptSpec                                │
   │  • Source of truth for the prompt text                   │
   └──────────────────────────────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │  2. RENDERER  (deterministic script)                     │
   │  ─────────────────────────────────                       │
   │  • Reads catalog                                         │
   │  • Composes prompt = STYLE_BASE + entry.prompt           │
   │  • Calls model (primary → fallback chain)                │
   │  • Post-processes with semantic bg removal               │
   │  • Writes <raster_dir>/<id>.png                          │
   │  • Emits per-entry log                                   │
   └──────────────────────────────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │  3. CONSUMER  (typed registry)                           │
   │  ───────────────────────────────                         │
   │  • Maps id → static asset URL                            │
   │  • E.g. urls.ts in Vite, barrel export in npm pkg, etc.  │
   │  • Treated as a build artifact, regenerated on each run  │
   └──────────────────────────────────────────────────────────┘
```

**Invariants between layers:**

- The catalog MUST NOT reference model APIs directly.
- The renderer MUST NOT contain prompt text — only composition
  logic and model plumbing.
- The consumer MUST be generated from the catalog; it MUST NOT be
  hand-maintained.

## 4. Pipeline

The renderer executes the following sequence for each catalog entry.

### 4.1 Inputs

- The catalog (file path is implementation-defined).
- The style template `STYLE_BASE` (a string constant in the renderer).
- The active palette presets (string constants in the renderer).
- The API key for the model (from environment or `.env`).
- `<raster_dir>` (the output directory).

### 4.2 Steps

For each entry `e` in the catalog:

1. **Compose prompt.** `prompt = STYLE_BASE + "\n\n" + e.palette + " " + e.prompt`.
2. **Generate.** Call the primary model with the prompt and the
   project's required config (aspect ratio, output mime, safety
   settings).
3. **On primary failure, fall back.** Call the fallback model with
   the same prompt. If the fallback also fails, follow F4 in §7.
4. **Remove background.** The post-processor MUST use a semantic
   salient-object model (e.g. `rembg` with `isnet-general-use`).
   Pixel-threshold background removal MUST NOT be used — diffusion
   model outputs have non-white backgrounds by construction.
5. **Validate output.** Confirm the result is a valid PNG with an
   alpha channel. If not, treat as a failure for this entry (F5).
6. **Write file.** Save to `<raster_dir>/<e.id>.png`. Overwrite
   if it exists.
7. **Log.** Emit `id`, model used, output size in bytes, and elapsed
   time. On failure, emit the error and continue.

### 4.3 Modes

- **Single mode** (`renderer <id>...`): generate only the given
  entries. Failure on any entry exits non-zero.
- **Batch mode** (`renderer --all`): generate every entry. Failure
  on any entry is logged but does NOT abort the batch; the process
  exits non-zero at the end if any entry failed.
- **List mode** (`renderer --list`): print the catalog ids and exit.
  MUST NOT make any model calls.

## 5. Data Model

### 5.1 The style template (`STYLE_BASE`)

A single string constant, owned by the renderer, that is prepended
verbatim to every composed prompt. It defines:

- The **aesthetic style** (e.g. "Flat vector illustration, Solar
  Punk Latin American style").
- **Negative constraints** (no gradients, no shading, no drop
  shadows, no background, no text, no labels, no watermarks, no
  borders).
- The **palette block**: a literal list of named hex tokens that
  the prompt author is expected to use. Hex values MUST appear
  only in this block; catalog entries reference tokens by name
  (e.g. "deep purple") rather than by hex.
- The **composition constraint** (single isolated element, centered,
  no scene, generous transparent padding, small-size readability).

The renderer MUST keep `STYLE_BASE` identical across all entries in
a single batch run. Drift in `STYLE_BASE` between runs is a known
source of visual inconsistency (F10 in §7).

### 5.2 Palette presets

A small set of named palette strings, each a short paragraph that
maps a mood to specific palette tokens. The renderer SHOULD expose
at least two presets:

- `ALIVE_PALETTE` — vibrant, hopeful.
- `WITHERED_PALETTE` — desaturated, diagnostic.

Catalog entries reference a preset by name, not by inlining its
text. The renderer expands the name to the preset's text at
composition time.

### 5.3 Catalog schema

Each catalog entry MUST conform to:

```yaml
id: string            # REQUIRED. kebab-case, stable. Pattern: ^[a-z]+--[a-z0-9-]+$
prompt: string        # REQUIRED. 1–3 sentences describing the subject.
palette: enum         # REQUIRED. One of the declared palette preset names.
metaphor: string      # REQUIRED. 1 sentence: the political/narrative meaning.
constraints:          # OPTIONAL. Overrides for global constraints.
  no_text: bool       # Default true.
  max_colors: int     # Default 4.
  no_numbers: bool    # Default true.
```

**Example entry:**

```yaml
id: arbol--marchito
palette: WITHERED_PALETTE
prompt: >
  A single dead tree: sparse bare branches with no leaves,
  dry cracked trunk, exposed withered roots at the base.
metaphor: >
  Metaphor: public science budget frozen and going nowhere.
constraints:
  max_colors: 3
```

The composed full prompt sent to the model is:

```
{STYLE_BASE}

{WITHERED_PALETTE}

A single dead tree: sparse bare branches with no leaves,
dry cracked trunk, exposed withered roots at the base.
```

The metaphor is included by the renderer as the final sentence of
the composed prompt, separated by a blank line.

## 6. Authoring Rules

These rules apply to any agent (LLM or human) writing a new catalog
entry. The renderer SHOULD validate catalog entries against them and
reject malformed ones before invoking the model.

### 6.1 Identifier (`id`)

- MUST be kebab-case, lowercase only.
- MUST match `^[a-z]+--[a-z0-9-]+$` (two segments separated by `--`).
- The first segment names the **narrative domain** (e.g. `arbol`,
  `ave`, `agua`, `ministerio`, `rev`).
- The second segment names the **descriptor** (e.g. `marchito`,
  `libre`, `represada`, `vacio`).
- Variants under exploration append a letter: `id-a`, `id-b`,
  `id-c`, `id-d`. Once approved, the chosen variant is promoted by
  renaming it to `<id>` (no letter) and the others are deleted.
- The id MUST NOT change once an asset has been referenced by any
  consumer. Renaming an id is a breaking change.

### 6.2 Prompt text

- MUST describe the **subject** in 1–3 sentences.
- MUST end with a metaphor sentence beginning "Metaphor:".
- MUST NOT contain language the model can interpret as photographic
  (e.g. "photo of", "realistic", "8K"). See §2.2.
- MUST NOT exceed 600 characters total (subject + metaphor).
- MUST reference palette tokens by name, NEVER by hex.
- Numbers are allowed in the metaphor text but the model is told
  (via the `no_numbers` constraint) not to render them visually.

### 6.3 Composition rules

- Each entry MUST describe a **single isolated element** on a
  transparent background.
- The element MUST be centered, with generous transparent padding
  on all sides.
- The element MUST be readable at small sizes (e.g. 64×64 px).
  The renderer SHOULD include a "silhouette readable from
  distance" phrase in `STYLE_BASE` to encode this requirement to
  the model.

### 6.4 Variant exploration

When iterating on a layout:

1. Create entries `<id>-a`, `<id>-b`, `<id>-c` with materially
   different compositions.
2. Render all variants in single mode.
3. The curator picks one. The chosen letter is **promoted** by
   renaming it to `<id>` (no letter) and the others are deleted.
4. The promotion SHOULD be a single commit with the message
   `promote <id>-{a|b|c|d} → <id>`.

## 7. Failure Modes

| ID  | Cause                                       | Behaviour                                                                                                                 |
| --- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| F1  | API key missing                             | Exit non-zero with a message naming the env var and the `.env` path. MUST NOT call the model.                             |
| F2  | Unknown `id` passed                         | Exit non-zero with the list of valid ids (use `--list`). MUST NOT call the model.                                         |
| F3  | Primary model refusal                       | Automatically fall back to the secondary model. Log which model succeeded.                                                 |
| F4  | Both models fail                            | Single mode: exit non-zero. Batch mode: log the error, continue with the next entry, exit non-zero at the end.            |
| F5  | Output not RGBA                             | Treat as F4 (output rejected).                                                                                            |
| F6  | Output size below lower bound               | Treat as F4. Lower bound SHOULD be 4 KB.                                                                                  |
| F7  | `rembg` failure on a single entry           | Treat as F4.                                                                                                              |
| F8  | `<raster_dir>` not writable                 | Exit non-zero before the loop starts.                                                                                     |
| F9  | Catalog file missing or malformed           | Exit non-zero with the validation error.                                                                                  |
| F10 | Style template drift between runs           | Log a warning if `STYLE_BASE` hash differs from the last run. Storage location is an open question (§11).                |

## 8. Validation Checklist

After the renderer finishes, an agent (or a CI step) SHOULD run the
following checks. The renderer MAY expose a `--validate` flag that
runs them without re-generating.

- [ ] **V1 — File presence.** For every catalog id, a file exists at
  `<raster_dir>/<id>.png`.
- [ ] **V2 — Dimensions.** Every PNG is the configured size
  (default 2048×2048, square).
- [ ] **V3 — Mode.** Every PNG is `RGBA` (not `RGB`, not `P`).
- [ ] **V4 — Transparent border.** The four edge rows/columns of
  every PNG have alpha = 0 for at least 95% of their pixels.
- [ ] **V5 — Palette conformance.** The dominant non-transparent
  colors in every PNG are within Euclidean distance `ΔE ≤ 30`
  of a declared palette token. This check is approximate and MAY
  be skipped if the project does not have a palette.
- [ ] **V6 — No text (optional, best-effort).** A CLIP- or
  OCR-based detector reports no text. This check is brittle and
  is best-effort; the prompt is the primary enforcement.
- [ ] **V7 — Catalog parity.** The set of `*.png` filenames in
  `<raster_dir>` exactly matches the set of catalog ids. Extra
  files SHOULD be reported (not deleted automatically).

## 9. Adaptation Guide

To fork this pattern into a new project, an agent SHOULD follow
these steps in order.

1. **Choose the model backend.** Pick the image model (Imagen,
   DALL·E, Stable Diffusion, local) and document the model id in
   the renderer. Pin the id; do not float.
2. **Define the style template.** Write the project's `STYLE_BASE`
   in plain prose: aesthetic, negative constraints, palette block
   (named tokens, no hex outside the block), composition rules.
3. **Declare palette tokens.** List 8–12 named colors with their
   hex values. These tokens are the only hex values that will ever
   appear in a composed prompt.
4. **Declare palette presets.** Define 2–4 named palettes that map
   moods to subsets of the tokens. The catalog references presets
   by name.
5. **Define the domain taxonomy.** Decide the first segments of
   the `id` namespace (e.g. `agua`, `trenza`, `rev`, …). 6–12
   domains is typical.
6. **Author 5–10 seed entries.** Cover each domain at least once
   with a strong, on-brand example. The seed set establishes the
   visual language; subsequent entries follow from it.
7. **Wire the renderer.** Implement the four steps from §4.2
   (compose, generate, post-process, write). Use semantic bg
   removal (`rembg isnet-general-use` or equivalent) — never pixel
   threshold.
8. **Wire the consumer.** Generate a typed registry from the
   catalog (e.g. `urls.ts` for Vite, barrel exports for npm).
   Treat the registry as a build artifact.
9. **Run the validation checklist.** §8.
10. **Iterate variants.** Use the variant convention from §6.4 to
    explore compositions before promoting canonical entries.

## 10. Reference Implementation

The reference implementation is
`carrousel_CTeI/scripts/generate_assets.py`. It is a Python script
with PEP 723 inline metadata, executed via `uv run`. It uses
`google-genai` to call `imagen-4.0-generate-001` with a fallback
to `gemini-3-pro-image-preview`.

**Known drift between this SPEC and the reference implementation
that an agent SHOULD be aware of when forking:**

- The reference docstring still says "Imagen 3" although the code
  calls Imagen 4. The code is the source of truth.
- The reference ships a `remove_white_background` helper using a
  pixel threshold (`>= 240`). This helper MUST NOT be used for
  diffusion outputs. The reference also ships a `remove_bg.py`
  script using `rembg isnet-general-use`; a forked renderer
  SHOULD prefer that path and drop the threshold helper.
- The reference inlines the prompt text in the renderer. A forked
  implementation SHOULD externalise the catalog to a separate
  data file (`.yaml` / `.json`) so the catalog can be authored
  without touching the renderer.

## 11. Open Questions

- **Prompt versioning.** When a prompt is updated, the old rendered
  PNG becomes stale. The catalog SHOULD support a `version` field
  and the renderer SHOULD support `--regen-from-version v1`.
  Decision deferred.
- **Style template drift detection.** A hash of `STYLE_BASE`
  SHOULD be persisted between runs and a warning emitted on change
  (F10). Storage location (`.style-base-hash` in `<raster_dir>`,
  sidecar file, or config file) is undecided.
- **Automatic "no text" enforcement.** A CLIP- or OCR-based
  detector is brittle for non-Latin scripts. An LLM-as-judge pass
  on a small random sample is the current best option; integration
  point is undecided.
- **Structured image APIs.** Some models now return JSON with
  masks and layers. Migrating to such an API would let the
  pipeline apply a guaranteed-clean transparent background at
  generation time, removing the need for `rembg`. Migration cost
  and benefit are undecided.
- **Multi-model ensemble.** Different models excel at different
  aesthetic regimes (flat illustration vs. organic illustration).
  A per-domain model-routing table is a possible v2 feature.
