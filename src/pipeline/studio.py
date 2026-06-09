"""Modo interactivo AI-in-the-Loop (D-021/D-022): checkpoint de keyframe.

Flujo por etapas con estado en el proyecto:
  gen_keyframes  -> N candidatos/escena + hoja de contactos (humano revisa)
  record_picks   -> persiste la elección del humano (selections.yaml)
  render         -> genera el video con los keyframes elegidos (reusa run_project)

`parse_picks` es lógica pura (testeable); la generación/render es I/O (smoke).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from .config import Config
from .contact_sheet import build_contact_sheet, write_and_open
from .keyframe import KeyframeGenerator, build_styled_prompt
from .naming import readable_name, semantic_slug
from .project import (
    Character,
    Project,
    ProjectSpec,
    _resolve_under,
    cache_key,
    character_refs,
    effective_shots,
    relativize,
    resolve_refs,
)
from .runner import _keyframe_inputs, run_project

logger = logging.getLogger(__name__)


def _alias(project: Project, subdir: str, prefix: str, slug: str, idx: int, src: Path) -> Path:
    """Copia legible (humano-facing) de un artefacto cacheado por hash (D-026).

    El caché sigue siendo la verdad (`src`); esto es solo el nombre que el humano
    ve y que puede pasar a `--keyframe`/`--face`. Devuelve la ruta del alias.
    """
    dest_dir = project.dir / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / readable_name(prefix, slug, idx, src.suffix or ".png")
    dest.write_bytes(Path(src).read_bytes())
    return dest


def parse_picks(items: list[str]) -> dict[str, int]:
    """Convierte ['s1=2', 's3=0'] -> {'s1': 2, 's3': 0}. Lógica pura."""
    picks: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Formato inválido '{item}'. Usa escena=indice (p.ej. s1=2).")
        sid, _, idx = item.partition("=")
        try:
            picks[sid.strip()] = int(idx)
        except ValueError:
            raise ValueError(f"Índice no entero en '{item}'.")
    return picks


def parse_overrides(items: list[str]) -> dict[str, Path]:
    """Convierte ['s1=ruta/a.png', 's2=b.png'] -> {'s1': Path('ruta/a.png'), ...}.

    Para inyectar un artefacto ya elegido **directo** (D-025): el flag `--keyframe`
    de `render` o `--face` de `pick-cast`, sin pasar por el ciclo de candidatos.
    Lógica pura (no toca disco); parte en el **primer** '=' para tolerar rutas
    Windows (`C:\\...`). La existencia del archivo la valida quien lo consume.
    """
    out: dict[str, Path] = {}
    for item in items:
        sid, sep, raw = item.partition("=")
        if not sep:
            raise ValueError(f"Formato inválido '{item}'. Usa clave=ruta (p.ej. s1=keyframes/s1.png).")
        ruta = raw.strip()
        if not ruta:
            raise ValueError(f"Ruta vacía en '{item}'.")
        out[sid.strip()] = Path(ruta)
    return out


# --- Checkpoint de casting / look-dev (Sprint 4.6) -------------------------

def apply_casting(characters: dict[str, Character], casting: dict[str, str]) -> None:
    """Sobreescribe la referencia canónica del personaje con la cara elegida (in place)."""
    for name, chosen in casting.items():
        if name in characters:
            characters[name].refs = [Path(chosen)]


def load_casting(project: Project) -> dict[str, str]:
    path = project.dir / "casting.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


async def cast(project: Project, spec: ProjectSpec, cfg: Config, n: int,
               open_sheet: bool = True) -> Path:
    """Genera N caras candidatas por personaje con `design` (multi-imagen + prompt)."""
    designed = {name: ch for name, ch in spec.characters.items() if ch.design}
    if not designed:
        raise RuntimeError("Ningún personaje tiene 'design:' en project.yaml.")
    keyframer = KeyframeGenerator(cfg.style, out_dir=project.dir / "_scratch")
    groups: dict[str, list[Path]] = {}
    manifest: dict[str, list[str]] = {}

    for name, ch in designed.items():
        ref_sig = sorted(str(r) for r in ch.design.refs)
        refs_resolved = resolve_refs(project.dir, ch.design.refs)  # project-relative -> abs
        paths: list[Path] = []        # hash (verdad del caché, estable para pick-cast)
        display: list[Path] = []      # alias legibles (<personaje>_cara_<idx>.png)
        for i in range(n):
            try:  # robustez: un candidato que falla no tira los demás
                key = cache_key("cast", {
                    "character": name, "prompt": ch.design.prompt,
                    "refs": ref_sig, "ref_model": cfg.style.keyframe.ref_model, "seed": i,
                })
                hit = project.cache_lookup("cast", key, ".png")
                if hit is not None:
                    stored = hit
                    logger.info("[%s] cara %d/%d (cache hit)", name, i + 1, n)
                else:
                    logger.info("[%s] cara %d/%d | generando...", name, i + 1, n)
                    tmp = await keyframer.generate_design(ch.design.prompt, refs_resolved, seed=i)
                    stored = project.cache_store("cast", key, tmp, ".png")
                alias = _alias(project, "faces", name, "cara", i, stored)
                paths.append(stored)
                display.append(alias)
                logger.info("[%s] cara %d/%d lista: %s", name, i + 1, n, alias.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] cara %d/%d FALLO: %s", name, i + 1, n, exc)
                logger.debug("[%s] traceback", name, exc_info=True)
        groups[name] = display
        manifest[name] = [str(p) for p in paths]

    (project.dir / "cast_candidates.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    html = build_contact_sheet(f"Casting · {spec.slug} (elige con: pipeline pick-cast)", groups)
    return write_and_open(html, project.dir / "cast_review.html", open_browser=open_sheet)


def record_cast_picks(project: Project, picks: dict[str, int]) -> Path:
    """Fija la cara canónica elegida por personaje (casting.yaml)."""
    cand_path = project.dir / "cast_candidates.yaml"
    if not cand_path.exists():
        raise RuntimeError("No hay candidatos de casting; corre 'pipeline cast <proj>' primero.")
    candidates = yaml.safe_load(cand_path.read_text(encoding="utf-8")) or {}
    casting = load_casting(project)
    for name, idx in picks.items():
        cands = candidates.get(name)
        if not cands:
            raise ValueError(f"No hay candidatos de casting para '{name}'.")
        if not 0 <= idx < len(cands):
            raise ValueError(f"Índice {idx} fuera de rango para '{name}' (0..{len(cands) - 1}).")
        # Persiste project-relative (portable, D-044): la cara vive en cache/
        # del proyecto -> queda como `cache/cast/<hash>.png`.
        casting[name] = relativize(project.dir, cands[idx])
    (project.dir / "casting.yaml").write_text(
        yaml.safe_dump(casting, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return project.dir / "casting.yaml"


def set_cast_faces(project: Project, faces: dict[str, Path]) -> Path:
    """Fija caras canónicas **directas** (D-025), sin pasar por `cast`/`pick-cast`.

    Para cuando la cara del personaje ya existe (de afuera o decidida): se toma,
    no se elige. Escribe en `casting.yaml` (lo mismo que `pick-cast`), así las
    escenas la heredan vía `apply_casting`.

    Las rutas se resuelven contra `project.dir` (formato del yaml: project-
    relative, p.ej. `refs/x.png`). Absolutas se respetan.
    """
    casting = load_casting(project)
    for name, path in faces.items():
        resolved = _resolve_under(project.dir, path)
        if not resolved.exists():
            raise RuntimeError(f"La cara directa de '{name}' no existe: {resolved}")
        casting[name] = relativize(project.dir, resolved)  # portable (D-044)
    (project.dir / "casting.yaml").write_text(
        yaml.safe_dump(casting, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return project.dir / "casting.yaml"


async def gen_keyframes(project: Project, spec: ProjectSpec, cfg: Config, n: int,
                        open_sheet: bool = True, concurrency: int = 5) -> Path:
    """Genera N candidatos de keyframe por escena en paralelo (semaforo=concurrency).

    Todas las (escena x candidato) se lanzan a la vez limitadas por el semaforo.
    fal.ai flux-lora soporta ~10 requests simultaneos en plan Pro; 5 es seguro.
    """
    keyframer = KeyframeGenerator(cfg.style, out_dir=project.dir / "_scratch")
    sem = asyncio.Semaphore(concurrency)

    # Pre-computa metadatos por escena (sincrono, sin I/O)
    scene_meta = []
    for scene in spec.scenes:
        refs = character_refs(scene, spec.characters)
        scene.character_refs = refs
        refs_resolved = resolve_refs(project.dir, refs)
        ref_sig = sorted(str(r) for r in refs)
        anchor = effective_shots(scene)[0]
        styled = build_styled_prompt(scene, cfg.style, anchor.framing)
        slug = semantic_slug(f"{scene.prompt} {anchor.framing}".strip())
        scene_meta.append((scene, refs_resolved, ref_sig, anchor, styled, slug))

    async def _one(scene, refs_resolved, ref_sig, anchor, styled, slug, i):
        """Genera un solo candidato bajo el semaforo."""
        async with sem:
            inputs = _keyframe_inputs(styled, cfg, ref_sig)
            inputs["seed"] = i
            key = cache_key("keyframe", inputs)
            hit = project.cache_lookup("keyframes", key, ".png")
            if hit is not None:
                logger.info("[%s] keyframe %d/%d (cache hit)", scene.id, i + 1, n)
                stored = hit
            else:
                logger.info("[%s] keyframe %d/%d | generando...", scene.id, i + 1, n)
                tmp = await keyframer.generate(scene, ref_images=refs_resolved,
                                               seed=i, framing=anchor.framing)
                stored = project.cache_store("keyframes", key, tmp, ".png")
            alias = _alias(project, "keyframes", scene.id, slug, i, stored)
            logger.info("[%s] keyframe %d/%d listo: %s", scene.id, i + 1, n, alias.name)
            return stored, alias

    # Lanza todas las tareas en paralelo, preserva (scene_idx, candidate_idx) para reensamblar
    tasks = [
        (s_idx, i, asyncio.ensure_future(_one(*meta, i)))
        for s_idx, meta in enumerate(scene_meta)
        for i in range(n)
    ]

    results: dict[int, list[tuple[int, Path, Path]]] = {i: [] for i in range(len(spec.scenes))}
    raw = await asyncio.gather(*(t for _, _, t in tasks), return_exceptions=True)

    for (s_idx, i, _), outcome in zip(tasks, raw):
        scene = spec.scenes[s_idx]
        if isinstance(outcome, Exception):
            logger.error("[%s] keyframe %d/%d FALLO: %s", scene.id, i + 1, n, outcome)
            logger.debug("[%s] traceback", scene.id, exc_info=outcome)
        else:
            stored, alias = outcome
            results[s_idx].append((i, stored, alias))

    # Reensambla en orden de candidato (gather no garantiza orden interno por escena)
    groups: dict[str, list[Path]] = {}
    manifest: dict[str, list[str]] = {}
    for s_idx, meta in enumerate(scene_meta):
        scene = spec.scenes[s_idx]
        ordered = sorted(results[s_idx], key=lambda x: x[0])
        groups[scene.id] = [alias for _, _, alias in ordered]
        manifest[scene.id] = [str(stored) for _, stored, _ in ordered]

    project.candidates_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    html = build_contact_sheet(f"Keyframes · {spec.slug} (elige con: pipeline pick)", groups)
    return write_and_open(html, project.dir / "keyframes_review.html", open_browser=open_sheet)


async def gen_keyframes_scene(
    project: Project, spec: ProjectSpec, cfg: Config,
    scene_id: str, n: int,
    prompt_tweak: str = "",
) -> None:
    """Genera N keyframes para UNA escena y hace MERGE en candidates.yaml existente.

    `prompt_tweak` se concatena al framing del plano 1 antes de pasar por el
    style template — cambia el cache key sin tocar el prompt base de la escena.
    Usa seed offset = len(candidatos actuales) para nunca pisar entradas previas.
    """
    scene = next((s for s in spec.scenes if s.id == scene_id), None)
    if scene is None:
        raise ValueError(f"Escena '{scene_id}' no encontrada en el proyecto.")

    keyframer = KeyframeGenerator(cfg.style, out_dir=project.dir / "_scratch")
    refs = character_refs(scene, spec.characters)
    scene.character_refs = refs
    refs_resolved = resolve_refs(project.dir, refs)
    ref_sig = sorted(str(r) for r in refs)
    anchor = effective_shots(scene)[0]

    framing = f"{anchor.framing}, {prompt_tweak}".strip(", ") if prompt_tweak else anchor.framing
    styled = build_styled_prompt(scene, cfg.style, framing)
    slug = semantic_slug(f"{scene.prompt} {framing}".strip())

    manifest: dict[str, list[str]] = {}
    if project.candidates_path.exists():
        manifest = yaml.safe_load(project.candidates_path.read_text(encoding="utf-8")) or {}
    existing = manifest.get(scene_id, [])
    seed_offset = len(existing)  # seeds distintos = cache keys distintos

    new_paths: list[str] = []
    for i in range(n):
        seed = seed_offset + i
        try:
            inputs = _keyframe_inputs(styled, cfg, ref_sig)
            inputs["seed"] = seed
            key = cache_key("keyframe", inputs)
            hit = project.cache_lookup("keyframes", key, ".png")
            if hit is not None:
                stored = hit
                logger.info("[%s] keyframe seed=%d (cache hit)", scene_id, seed)
            else:
                logger.info("[%s] keyframe seed=%d | generando...", scene_id, seed)
                tmp = await keyframer.generate(scene, ref_images=refs_resolved,
                                               seed=seed, framing=framing)
                stored = project.cache_store("keyframes", key, tmp, ".png")
            _alias(project, "keyframes", scene_id, slug, seed, stored)
            new_paths.append(str(stored))
            logger.info("[%s] keyframe seed=%d listo", scene_id, seed)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] keyframe seed=%d FALLO: %s", scene_id, seed, exc)
            logger.debug("[%s] traceback", scene_id, exc_info=True)

    manifest[scene_id] = existing + new_paths
    project.candidates_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def add_candidate_upload(project: Project, scene_id: str, data: bytes, suffix: str) -> Path:
    """Guarda una imagen subida manualmente como candidato de keyframe.

    La imagen entra al pool de candidatos igual que un generado — el humano
    la selecciona normalmente. Usa hash del contenido para evitar duplicados.
    """
    import hashlib

    if not suffix.startswith("."):
        suffix = f".{suffix}"
    key = hashlib.sha256(data).hexdigest()[:16]
    dest = project.cache_dir / "keyframes" / f"upload_{key}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    manifest: dict[str, list[str]] = {}
    if project.candidates_path.exists():
        manifest = yaml.safe_load(project.candidates_path.read_text(encoding="utf-8")) or {}
    existing = manifest.get(scene_id, [])
    if str(dest) not in existing:
        manifest[scene_id] = existing + [str(dest)]
        project.candidates_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    return dest


def set_project_music(project: Project, spec: ProjectSpec, src: Path) -> None:
    """Fija la musica de fondo del proyecto y persiste en project.yaml."""
    from .project import write_spec
    spec.music = src.resolve()
    write_spec(spec, project.spec_path)


def record_picks(project: Project, picks: dict[str, int]) -> Path:
    """Valida y persiste la elección humana (selections.yaml). Resumible."""
    if not project.candidates_path.exists():
        raise RuntimeError("No hay candidatos; corre 'pipeline keyframes <proj>' primero.")
    candidates = yaml.safe_load(project.candidates_path.read_text(encoding="utf-8")) or {}
    selections = {}
    if project.selections_path.exists():
        selections = yaml.safe_load(project.selections_path.read_text(encoding="utf-8")) or {}

    for sid, idx in picks.items():
        cands = candidates.get(sid)
        if not cands:
            raise ValueError(f"No hay candidatos para '{sid}'.")
        if not 0 <= idx < len(cands):
            raise ValueError(f"Índice {idx} fuera de rango para '{sid}' (0..{len(cands) - 1}).")
        # Persiste project-relative (portable, D-044): el candidato vive en
        # cache/ del proyecto -> queda como `cache/keyframes/<hash>.png`.
        selections[sid] = relativize(project.dir, cands[idx])

    project.selections_path.write_text(
        yaml.safe_dump(selections, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return project.selections_path


def prune_selections(project: Project, scene_ids: list[str]) -> list[str]:
    """Guard de [D-022]: al editar el storyboard (renombrar/eliminar/reordenar
    escenas) la selección de keyframes se llavea por id de escena. Descarta las
    entradas cuyo id ya no existe para no dejar `selections.yaml` corrupto.
    Devuelve los ids descartados. Reordenar no rompe (el id se conserva)."""
    if not project.selections_path.exists():
        return []
    selections = yaml.safe_load(project.selections_path.read_text(encoding="utf-8")) or {}
    valid = set(scene_ids)
    dropped = [sid for sid in selections if sid not in valid]
    if dropped:
        kept = {sid: v for sid, v in selections.items() if sid in valid}
        project.selections_path.write_text(
            yaml.safe_dump(kept, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    return dropped


async def render(project: Project, spec: ProjectSpec, cfg: Config,
                 keyframe_overrides: dict[str, Path] | None = None,
                 concurrency: int = 1):
    """Genera el video con los keyframes elegidos por escena.

    Dos fuentes de keyframe, con precedencia (D-025): el flag `--keyframe`
    (`keyframe_overrides`, el humano ya tiene la imagen) **gana** sobre la
    selección persistida (`selections.yaml`, el ciclo de candidatos). Una escena
    queda satisfecha por cualquiera de las dos.
    """
    # Rutas resueltas para I/O contra el proyecto (project-relative -> abs, D-044):
    # selections.yaml y --keyframe son portables (relativos al proyecto).
    flag: dict[str, Path] = {}
    for sid, p in (keyframe_overrides or {}).items():  # error temprano si no existe
        resolved = _resolve_under(project.dir, p)
        if not resolved.exists():
            raise RuntimeError(f"El keyframe directo de '{sid}' no existe: {resolved}")
        flag[sid] = resolved

    selections = {}
    if project.selections_path.exists():
        selections = yaml.safe_load(project.selections_path.read_text(encoding="utf-8")) or {}

    merged: dict[str, Path] = {sid: _resolve_under(project.dir, p) for sid, p in selections.items()}
    merged.update(flag)  # el flag tiene precedencia (D-025)

    missing = [s.id for s in spec.scenes if s.id not in merged]
    if missing:
        raise RuntimeError(
            f"Faltan keyframes para: {missing}. "
            "Usa 'pipeline pick <proj> escena=idx' o 'pipeline render <proj> --keyframe escena=ruta'."
        )
    return await run_project(project, spec, cfg, keyframe_overrides=merged,
                             concurrency=concurrency)
