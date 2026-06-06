"""Modo interactivo AI-in-the-Loop (D-021/D-022): checkpoint de keyframe.

Flujo por etapas con estado en el proyecto:
  gen_keyframes  -> N candidatos/escena + hoja de contactos (humano revisa)
  record_picks   -> persiste la elección del humano (selections.yaml)
  render         -> genera el video con los keyframes elegidos (reusa run_project)

`parse_picks` es lógica pura (testeable); la generación/render es I/O (smoke).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .config import Config
from .contact_sheet import build_contact_sheet, write_and_open
from .keyframe import KeyframeGenerator, build_styled_prompt
from .naming import readable_name, semantic_slug
from .project import Character, Project, ProjectSpec, cache_key, character_refs, effective_shots
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
                    tmp = await keyframer.generate_design(ch.design.prompt, ch.design.refs, seed=i)
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
        casting[name] = cands[idx]
    (project.dir / "casting.yaml").write_text(
        yaml.safe_dump(casting, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return project.dir / "casting.yaml"


def set_cast_faces(project: Project, faces: dict[str, Path]) -> Path:
    """Fija caras canónicas **directas** (D-025), sin pasar por `cast`/`pick-cast`.

    Para cuando la cara del personaje ya existe (de afuera o decidida): se toma,
    no se elige. Escribe en `casting.yaml` (lo mismo que `pick-cast`), así las
    escenas la heredan vía `apply_casting`.
    """
    casting = load_casting(project)
    for name, path in faces.items():
        if not Path(path).exists():
            raise RuntimeError(f"La cara directa de '{name}' no existe: {path}")
        casting[name] = str(path)
    (project.dir / "casting.yaml").write_text(
        yaml.safe_dump(casting, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return project.dir / "casting.yaml"


async def gen_keyframes(project: Project, spec: ProjectSpec, cfg: Config, n: int,
                        open_sheet: bool = True) -> Path:
    """Genera N candidatos de keyframe por escena y escribe la hoja de contactos."""
    keyframer = KeyframeGenerator(cfg.style, out_dir=project.dir / "_scratch")
    groups: dict[str, list[Path]] = {}
    manifest: dict[str, list[str]] = {}

    for scene in spec.scenes:
        refs = character_refs(scene, spec.characters)
        scene.character_refs = refs
        ref_sig = sorted(str(r) for r in refs)
        anchor = effective_shots(scene)[0]  # el keyframe elegido = plano 1 (D-028)
        styled = build_styled_prompt(scene, cfg.style, anchor.framing)
        slug = semantic_slug(f"{scene.prompt} {anchor.framing}".strip())  # nombre legible (D-026)
        paths: list[Path] = []        # hash (verdad del caché, estable para pick/render)
        display: list[Path] = []      # alias legibles (lo que ve el humano en la hoja)
        for i in range(n):
            try:  # robustez: un candidato que falla no tira los demás
                inputs = _keyframe_inputs(styled, cfg, ref_sig)
                inputs["seed"] = i  # candidato i: seed distinto -> imagen distinta
                key = cache_key("keyframe", inputs)
                hit = project.cache_lookup("keyframes", key, ".png")
                if hit is not None:
                    stored = hit
                    logger.info("[%s] keyframe %d/%d (cache hit)", scene.id, i + 1, n)
                else:
                    logger.info("[%s] keyframe %d/%d | generando...", scene.id, i + 1, n)
                    tmp = await keyframer.generate(scene, ref_images=refs, seed=i, framing=anchor.framing)
                    stored = project.cache_store("keyframes", key, tmp, ".png")
                alias = _alias(project, "keyframes", scene.id, slug, i, stored)
                paths.append(stored)
                display.append(alias)
                logger.info("[%s] keyframe %d/%d listo: %s", scene.id, i + 1, n, alias.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] keyframe %d/%d FALLO: %s", scene.id, i + 1, n, exc)
                logger.debug("[%s] traceback", scene.id, exc_info=True)
        groups[scene.id] = display
        manifest[scene.id] = [str(p) for p in paths]

    project.candidates_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    html = build_contact_sheet(f"Keyframes · {spec.slug} (elige con: pipeline pick)", groups)
    return write_and_open(html, project.dir / "keyframes_review.html", open_browser=open_sheet)


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
        selections[sid] = cands[idx]

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
                 keyframe_overrides: dict[str, Path] | None = None):
    """Genera el video con los keyframes elegidos por escena.

    Dos fuentes de keyframe, con precedencia (D-025): el flag `--keyframe`
    (`keyframe_overrides`, el humano ya tiene la imagen) **gana** sobre la
    selección persistida (`selections.yaml`, el ciclo de candidatos). Una escena
    queda satisfecha por cualquiera de las dos.
    """
    flag = keyframe_overrides or {}
    for sid, p in flag.items():  # error temprano y claro si la ruta no existe
        if not Path(p).exists():
            raise RuntimeError(f"El keyframe directo de '{sid}' no existe: {p}")

    selections = {}
    if project.selections_path.exists():
        selections = yaml.safe_load(project.selections_path.read_text(encoding="utf-8")) or {}

    merged: dict[str, Path] = {sid: Path(p) for sid, p in selections.items()}
    merged.update(flag)  # el flag tiene precedencia (D-025)

    missing = [s.id for s in spec.scenes if s.id not in merged]
    if missing:
        raise RuntimeError(
            f"Faltan keyframes para: {missing}. "
            "Usa 'pipeline pick <proj> escena=idx' o 'pipeline render <proj> --keyframe escena=ruta'."
        )
    return await run_project(project, spec, cfg, keyframe_overrides=merged)
