"""Core: la tira del animatic en solo-lectura (D-061).

`animatic_strip` recorre la cinta computando las MISMAS cache keys que el render
(dry=True) y mira el cache SIN generar (cero costo). Es la fuente de la página
Animatic y de la visibilidad de avance/costo en el status.
"""

from pathlib import Path

import yaml

from pipeline.config import load_config
from pipeline.contracts import Scene, Shot
from pipeline.project import Project, ProjectSpec
from pipeline.studio import animatic_strip

CONFIG_DIR = Path("config")


def _spec() -> ProjectSpec:
    return ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=4, shots=[
            Shot(action="x", duration_s=2, transition="cut"),
            Shot(action="y", duration_s=2),
        ]),
        Scene(id="s2", prompt="b", duration_s=3),  # 1 plano implícito
    ])


def _project(tmp_path: Path) -> Project:
    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    return proj


async def test_strip_lists_all_shots_without_generating(tmp_path):
    proj = _project(tmp_path)
    cfg = load_config(CONFIG_DIR, "lego")
    strip = await animatic_strip(proj, _spec(), cfg)
    assert [e["shot_id"] for e in strip] == ["s1", "s1.2", "s2"]
    # cache vacío: nada listo, nada generado (cero archivos nuevos en keyframes/)
    assert all(not e["ready"] and e["start"] is None and e["destino"] is None for e in strip)
    assert list((proj.cache_dir / "keyframes").iterdir()) == []


async def test_strip_carries_transition_and_duration(tmp_path):
    proj = _project(tmp_path)
    cfg = load_config(CONFIG_DIR, "lego")
    strip = await animatic_strip(proj, _spec(), cfg)
    by_id = {e["shot_id"]: e for e in strip}
    assert by_id["s1.2"]["transition_in"] == "cut"
    assert by_id["s2"]["duration_s"] == 3


async def test_strip_shows_picked_anchor_as_destino(tmp_path):
    proj = _project(tmp_path)
    anchor = proj.cache_dir / "keyframes" / "anchor.png"
    anchor.write_bytes(b"\x89PNG")
    proj.selections_path.write_text(
        yaml.safe_dump({"s1": "cache/keyframes/anchor.png"}), encoding="utf-8")
    cfg = load_config(CONFIG_DIR, "lego")
    strip = await animatic_strip(proj, _spec(), cfg)
    s1 = next(e for e in strip if e["shot_id"] == "s1")
    assert s1["destino"] and s1["destino"].endswith("anchor.png")  # el ancla elegida
    # D-070 (cámara-actúa): sin `lands`, el destino ES el plano -> listo sin apertura.
    assert s1["start"] is None and s1["ready"] is True


async def test_strip_is_quiet_at_info_level(tmp_path, caplog):
    # El strip dry (status/animatic) se recalcula en cada navegación: NO debe
    # emitir el INFO por-plano "destino directo (ancla)" que inundaba la consola.
    # En un render real (dry=False) ese log sigue siendo INFO (visible).
    import logging

    proj = _project(tmp_path)
    anchor = proj.cache_dir / "keyframes" / "anchor.png"
    anchor.write_bytes(b"\x89PNG")
    proj.selections_path.write_text(
        yaml.safe_dump({"s1": "cache/keyframes/anchor.png"}), encoding="utf-8")
    cfg = load_config(CONFIG_DIR, "lego")
    with caplog.at_level(logging.INFO, logger="pipeline"):
        await animatic_strip(proj, _spec(), cfg)
    assert not any("destino directo (ancla)" in r.message
                   for r in caplog.records if r.levelno >= logging.INFO)


async def test_strip_lands_shot_requires_both_poses(tmp_path):
    """D-070: un plano `lands` (interpola) NO está listo solo con el destino."""
    proj = _project(tmp_path)
    anchor = proj.cache_dir / "keyframes" / "anchor.png"
    anchor.write_bytes(b"\x89PNG")
    proj.selections_path.write_text(
        yaml.safe_dump({"s1": "cache/keyframes/anchor.png"}), encoding="utf-8")
    cfg = load_config(CONFIG_DIR, "lego")
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=2,
              shots=[Shot(action="x", duration_s=2, lands=True)]),
    ])
    strip = await animatic_strip(proj, spec, cfg)
    s1 = strip[0]
    assert s1["lands"] is True
    assert s1["destino"] and s1["start"] is None and s1["ready"] is False


# --- D-080: las poses fantasma -------------------------------------------------

def test_count_missing_poses_ignores_camera_acts_openings():
    """Tras D-070 la apertura existe SOLO en planos lands. Contarla en los demas
    prometia 'completar' poses que el motor jamas genera (el boton del Animatic
    pedia 21 poses fantasma y el contador no bajaba nunca)."""
    from pipeline.studio import count_missing_poses

    strip = [
        {"destino": "d.png", "start": None, "lands": False},   # camara-actua completa: 0
        {"destino": None,    "start": None, "lands": False},   # falta el destino: 1
        {"destino": "d.png", "start": None, "lands": True},    # lands sin apertura: 1
        {"destino": "d.png", "start": "s.png", "lands": True}, # lands completa: 0
        {"destino": None,    "start": None, "lands": True},    # lands sin nada: 2
    ]
    assert count_missing_poses(strip) == 4
