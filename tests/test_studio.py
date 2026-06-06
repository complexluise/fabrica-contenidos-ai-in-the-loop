"""Core Sprint 4.5: hoja de contactos + parseo de selecciones (AI-in-the-Loop).

Test-first. Solo la lógica pura; la generación/render se valida con smoke.
"""

from pathlib import Path

import pytest

from pipeline.contact_sheet import build_contact_sheet
from pipeline.studio import parse_overrides, parse_picks


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
