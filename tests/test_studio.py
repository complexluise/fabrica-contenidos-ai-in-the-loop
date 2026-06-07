"""Core Sprint 4.5: hoja de contactos + parseo de selecciones (AI-in-the-Loop).

Test-first. Solo la lógica pura; la generación/render se valida con smoke.
"""

from pathlib import Path

import pytest

from pipeline.contact_sheet import build_contact_sheet
from pipeline.studio import parse_overrides, parse_picks, resolve_refs


# --- contact sheet ----------------------------------------------------------

def test_contact_sheet_has_title_and_scenes():
    html = build_contact_sheet("Keyframes lego_demo", {
        "s1": [Path("a.png"), Path("b.png")],
        "s2": [Path("c.png")],
    })
    assert "Keyframes lego_demo" in html
    assert "s1" in html and "s2" in html


def test_contact_sheet_one_img_per_candidate():
    html = build_contact_sheet("t", {"s1": [Path("a.png"), Path("b.png"), Path("c.png")]})
    assert html.count("<img") == 3


def test_contact_sheet_labels_indices():
    html = build_contact_sheet("t", {"s1": [Path("a.png"), Path("b.png")]})
    # el humano elige por índice -> deben aparecer los índices
    assert "s1=0" in html and "s1=1" in html


# --- parse de selecciones ---------------------------------------------------

def test_parse_picks_single():
    assert parse_picks(["s1=2"]) == {"s1": 2}


def test_parse_picks_multiple():
    assert parse_picks(["s1=2", "s3=0"]) == {"s1": 2, "s3": 0}


def test_parse_picks_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_picks(["s1"])


def test_parse_picks_rejects_non_int_index():
    with pytest.raises(ValueError):
        parse_picks(["s1=x"])


# --- parse de overrides directos (D-025: inyectar keyframe por flag) ---------

def test_parse_overrides_single():
    assert parse_overrides(["s1=keyframes/a.png"]) == {"s1": Path("keyframes/a.png")}


def test_parse_overrides_multiple():
    out = parse_overrides(["s1=a.png", "s2=b.png"])
    assert out == {"s1": Path("a.png"), "s2": Path("b.png")}


def test_parse_overrides_keeps_windows_path():
    # La ruta puede traer '=' nunca, pero sí ':' y '\\' (Windows). Solo parte en el 1er '='.
    assert parse_overrides([r"s1=C:\imgs\a.png"]) == {"s1": Path(r"C:\imgs\a.png")}


def test_parse_overrides_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_overrides(["s1"])


def test_parse_overrides_rejects_empty_path():
    with pytest.raises(ValueError):
        parse_overrides(["s1="])


# --- resolución de refs project-relative ------------------------------------
# El `project.yaml` y los flags `--face` declaran rutas project-relative
# (p.ej. `refs/x.png`); hay que resolverlas contra `project.dir` antes de
# pasárselas al keyframer o validar existencia.

def test_resolve_refs_relative_against_base(tmp_path):
    base = tmp_path
    out = resolve_refs(base, [Path("refs/a.png"), Path("refs/b.png")])
    assert out == [base / "refs/a.png", base / "refs/b.png"]
    assert all(p.is_absolute() for p in out)


def test_resolve_refs_keeps_absolute_paths(tmp_path):
    abs_path = tmp_path / "abs.png"
    out = resolve_refs(tmp_path, [abs_path])
    assert out == [abs_path]


def test_set_cast_faces_resolves_relative_against_project_dir(tmp_path):
    """Bug original: `Path('refs/x.png').exists()` buscaba contra CWD, no
    contra el proyecto. El fix resuelve contra `project.dir`."""
    from pipeline.project import Project
    from pipeline.studio import set_cast_faces

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "refs").mkdir()
    face = project_dir / "refs" / "cara.png"
    face.write_bytes(b"x")

    proj = Project("proj", root=tmp_path)
    out = set_cast_faces(proj, {"juan": Path("refs/cara.png")})
    assert out.exists()
    import yaml as _y
    casting = _y.safe_load(out.read_text(encoding="utf-8"))
    assert casting["juan"].endswith("refs" + __import__("os").sep + "cara.png")


def test_set_cast_faces_raises_with_resolved_path_in_message(tmp_path):
    """El error debe mostrar la ruta **resuelta** (la que de verdad no existe),
    no la cruda del usuario, para que sea accionable."""
    from pipeline.project import Project
    from pipeline.studio import set_cast_faces

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    proj = Project("proj", root=tmp_path)
    with pytest.raises(RuntimeError, match=r"no existe"):
        set_cast_faces(proj, {"juan": Path("refs/missing.png")})
