"""Core: constructor del filtro drawtext para lower-thirds de marca (T3.4).

Solo la parte pura (construcción/escape del filtro). El burn con ffmpeg se valida
con smoke run.
"""

from pipeline.post import lower_third_filter


def test_filter_contains_text_and_drawtext():
    f = lower_third_filter("Marca X")
    assert "drawtext" in f and "Marca X" in f


def test_filter_escapes_colon():
    # Los ':' separan opciones en ffmpeg; deben escaparse dentro del texto.
    f = lower_third_filter("12:00 PM")
    assert "12\\:00 PM" in f


def test_filter_centers_at_bottom():
    f = lower_third_filter("hola")
    assert "x=(w-tw)/2" in f and "y=h-th-" in f
