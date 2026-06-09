"""Core: los ojos (D-041). Prompt + parseo tolerante + contexto/tiempos de frame.

La I/O (ffmpeg + Haiku) es smoke; aqui solo la logica pura.
"""

import pytest

from pipeline.describe import (
    _frame_times,
    _plano_context,
    describe_prompt,
    parse_description,
)


def test_prompt_incluye_contexto_y_pide_json():
    p = describe_prompt("beat: apertura | encuadre: plano general")
    assert "beat: apertura" in p
    assert "JSON" in p
    assert "usable" in p and "on_message" in p


def test_parse_description_json_limpio():
    out = parse_description('{"description":"un obrero","on_message":0.8,"usable":true,"issues":[]}')
    assert out == {"description": "un obrero", "on_message": 0.8, "usable": True, "issues": []}


def test_parse_description_tolera_texto_alrededor():
    txt = 'Claro:\n{"description":"x","on_message":0.5,"usable":false,"issues":["deforme"]}\nfin'
    out = parse_description(txt)
    assert out["usable"] is False
    assert out["issues"] == ["deforme"]


def test_parse_description_defaults_permisivos():
    # Campos faltantes -> usable True (permisivo) y valores neutros.
    out = parse_description('{"description":"algo"}')
    assert out["usable"] is True
    assert out["on_message"] == 0.0
    assert out["issues"] == []


def test_parse_description_sin_json_lanza():
    with pytest.raises(ValueError):
        parse_description("no hay json aqui")


def test_plano_context_arma_bits_y_omite_vacios():
    ctx = _plano_context({"beat": "cierre", "framing": "", "voiceover": "vota", "caption": None})
    assert "beat: cierre" in ctx
    assert "voz: vota" in ctx
    assert "encuadre" not in ctx  # vacio -> omitido


def test_plano_context_sin_datos():
    assert _plano_context({}) == "(sin contexto)"


def test_frame_times_escala_con_duracion():
    assert _frame_times(0) == [0.5]
    assert len(_frame_times(1.0)) == 1
    assert len(_frame_times(3.0)) == 2
    assert len(_frame_times(8.0)) == 3
    # el ultimo frame de un clip largo no se pasa del final
    assert _frame_times(8.0)[-1] <= 8.0
