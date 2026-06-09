"""Core: el artista (D-042). Seleccion de graficos desde el manifest.

El render con movis es smoke (extra [edit]); aqui solo la logica pura.
"""

from dataclasses import dataclass

from pipeline.graphics import _format_size, end_spec, lower_thirds, title_spec


@dataclass
class _Spec:
    slug: str = "demo"
    style: str = "lego"
    format: str = "9:16"
    title: str | None = None


def test_format_size_conocido_y_default():
    assert _format_size("9:16") == (1080, 1920)
    assert _format_size("16:9") == (1920, 1080)
    assert _format_size("1:1") == (1080, 1080)
    assert _format_size("raro") == (1080, 1920)  # default


def test_lower_thirds_filtra_captions_vacios_y_conserva_orden():
    planos = [
        {"base": "01_s1", "caption": "Vota", "duration_s": 3},
        {"base": "02_s1", "caption": "   ", "duration_s": 2},   # vacio -> fuera
        {"base": "03_s2", "caption": None, "duration_s": 2},    # None -> fuera
        {"base": "04_s2", "caption": "Conciencia", "duration_s": 4},
    ]
    lts = lower_thirds(planos)
    assert [lt["base"] for lt in lts] == ["01_s1", "04_s2"]
    assert lts[0] == {"base": "01_s1", "text": "Vota", "duration_s": 3.0}


def test_lower_thirds_vacio_si_no_hay_captions():
    assert lower_thirds([{"base": "01_s1", "caption": "", "duration_s": 1}]) == []


def test_title_spec_usa_title_o_slug():
    assert title_spec(_Spec(title="La Fractura"))["text"] == "La Fractura"
    assert title_spec(_Spec(title=None, slug="demo"))["text"] == "demo"
    assert "lego" in title_spec(_Spec())["subtitle"]


def test_end_spec_usa_title_o_slug():
    assert end_spec(_Spec(title="Fin"))["text"] == "Fin"
    assert end_spec(_Spec(title=None, slug="demo"))["text"] == "demo"
