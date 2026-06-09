"""L10 - El artista: motion graphics deterministas con movis (D-042).

movis genera los GRAFICOS (no compone el corte: eso lo hace mcp-video). Desde el
manifest del ultimo run produce, en `export/graphics/`:
- `lt_<base>.png` por plano con `caption` -> lower-third con alpha (caja
  semitransparente + texto + sombra). PNG RGBA = overlay robusto/transparente que
  mcp-video superpone por la duracion del plano.
- `title.mp4` / `end.mp4` -> placas de titulo y cierre (full-frame, fade-in).

La seleccion desde el manifest (`lower_thirds`/`title_spec`/`end_spec`/`_format_size`)
es logica pura (testeable, sin movis). `render_graphics` es I/O (movis, smoke) e
importa movis de forma perezosa -> el core se testea sin el extra `[edit]`.
"""

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path

from .export import _manifest_planos, numbered
from .project import Project, ProjectSpec

logger = logging.getLogger(__name__)

# Tamaños canonicos por formato (mismos que L8/deliver).
_SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}


def _format_size(fmt: str) -> tuple[int, int]:
    """Pixeles (w, h) del formato; default 9:16. Logica pura."""
    return _SIZES.get(str(fmt), (1080, 1920))


def lower_thirds(planos: list[dict]) -> list[dict]:
    """Un lower-third por plano con `caption` no vacio, en orden. Logica pura."""
    out: list[dict] = []
    for p in planos:
        cap = p.get("caption")
        if isinstance(cap, str) and cap.strip():
            out.append({
                "base": p["base"],
                "text": cap.strip(),
                "duration_s": float(p.get("duration_s") or 0),
            })
    return out


def title_spec(spec: ProjectSpec) -> dict:
    """Placa de titulo desde el spec. Logica pura."""
    return {"text": spec.title or spec.slug, "subtitle": f"{spec.style} · {spec.format}"}


def end_spec(spec: ProjectSpec) -> dict:
    """Placa de cierre desde el spec. Logica pura."""
    return {"text": spec.title or spec.slug}


# --- render (I/O, smoke; movis importado perezosamente) ---------------------

def _render_card(mv, size: tuple[int, int], card: dict, dest: Path, duration: float = 2.5) -> Path:
    """Placa full-frame con fondo + titulo (fade-in) -> .mp4."""
    w, h = size
    scene = mv.layer.Composition(size=size, duration=duration)
    scene.add_layer(mv.layer.Rectangle(size, color="#0a0a0a"))  # fondo
    scene.add_layer(
        mv.layer.Text(card["text"], font_size=int(h * 0.06), color="#ffffff"),
        name="title", position=(w // 2, int(h * 0.46)),
    )
    scene["title"].opacity.enable_motion().extend([0.0, 0.8], [0.0, 1.0], ["ease_out"])
    if card.get("subtitle"):
        scene.add_layer(
            mv.layer.Text(card["subtitle"], font_size=int(h * 0.028), color="#cccccc"),
            name="sub", position=(w // 2, int(h * 0.54)),
        )
        scene["sub"].opacity.enable_motion().extend([0.3, 1.1], [0.0, 1.0], ["ease_out"])
    scene.write_video(str(dest))
    return dest


def _render_lower_third(mv, Image, size: tuple[int, int], lt: dict, dest: Path) -> Path:
    """Lower-third con alpha (caja semitransparente + texto) -> PNG RGBA."""
    w, h = size
    dur = max(0.2, lt["duration_s"] or 2.0)
    scene = mv.layer.Composition(size=size, duration=dur)
    box_h = int(h * 0.13)
    box_y = int(h * 0.82)
    scene.add_layer(
        mv.layer.Rectangle((w, box_h), color="#0a0a0a"),
        name="box", position=(w // 2, box_y), opacity=0.55,
    )
    scene.add_layer(
        mv.layer.Text(lt["text"], font_size=int(h * 0.030), color="#ffffff"),
        name="txt", position=(w // 2, box_y),
    )
    scene["txt"].add_effect(mv.effect.DropShadow(offset=6.0))
    frame = scene(min(0.2, dur / 2))  # frame RGBA representativo (H, W, 4) uint8
    Image.fromarray(frame).save(str(dest))
    return dest


def render_graphics(project: Project, spec: ProjectSpec) -> Path:
    """Renderiza los graficos del ultimo run a `export/graphics/`. I/O (smoke)."""
    run = project.latest_run()
    if run is None or not run.manifest_path.exists():
        raise RuntimeError(
            f"No hay runs para '{project.slug}'. Corre 'pipeline render {project.slug}' primero.")
    planos = numbered(_manifest_planos(run))
    if not planos:
        raise RuntimeError("El manifest del ultimo run no tiene planos.")

    import movis as mv  # perezoso: el extra [edit] solo hace falta para renderizar
    from PIL import Image

    out_dir = project.dir / "export" / "graphics"
    out_dir.mkdir(parents=True, exist_ok=True)
    size = _format_size(spec.format)

    # movis pinta barras de progreso (tqdm con `█`) en stderr: las capturamos para
    # no contaminar — y, en Windows/cp1252, no crashear — la consola. Los errores
    # reales propagan como excepciones, no por este texto.
    with contextlib.redirect_stderr(io.StringIO()):
        _render_card(mv, size, title_spec(spec), out_dir / "title.mp4")
        for lt in lower_thirds(planos):
            _render_lower_third(mv, Image, size, lt, out_dir / f"lt_{lt['base']}.png")
        _render_card(mv, size, end_spec(spec), out_dir / "end.mp4")

    logger.info("graphics: %d lower-thirds + title/end en %s", len(lower_thirds(planos)), out_dir)
    return out_dir
