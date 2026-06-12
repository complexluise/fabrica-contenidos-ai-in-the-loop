"""Core Sprint 6.6: la escena compone planos (D-028).

Test-first del core puro: parseo de `Shot`/`Scene.shots`, `effective_shots`
(sintetiza 1 plano si no hay) y la composición de prompt `scene.prompt + framing`.
La expansión en el runner y el ensamblaje se validan con smoke.
"""

import types

from pipeline.contracts import Scene
from pipeline.keyframe import build_styled_prompt
from pipeline.project import effective_shots, load_project_spec

_style = types.SimpleNamespace(prompt_template="{scene_prompt} :: crochet")


def _scene(**kw):
    base = dict(id="s2", prompt="ciudad con mapa", duration_s=5)
    base.update(kw)
    return Scene(**base)


# --- composición de prompt: el plano EXTIENDE el de la escena -----------------

def test_build_styled_prompt_without_framing_unchanged():
    # Compat: sin framing, el prompt efectivo es el de la escena (clave de caché estable).
    assert build_styled_prompt(_scene(), _style) == "ciudad con mapa :: crochet"


def test_build_styled_prompt_appends_framing():
    out = build_styled_prompt(_scene(), _style, framing="extreme close-up on the map")
    assert out == "ciudad con mapa, extreme close-up on the map :: crochet"


# --- parseo de Shot / Scene.shots --------------------------------------------

def test_scene_parses_shots():
    s = _scene(shots=[
        {"framing": "wide", "duration_s": 2},
        {"framing": "close", "duration_s": 1.5, "voiceover": "hola"},
    ])
    assert len(s.shots) == 2
    assert s.shots[0].framing == "wide"
    assert s.shots[1].voiceover == "hola"


def test_scene_without_shots_is_empty_list():
    assert _scene().shots == []


# --- effective_shots: planos reales o 1 sintetizado (compat) ------------------

def test_effective_shots_returns_authored():
    shots = effective_shots(_scene(shots=[{"framing": "wide", "duration_s": 2}]))
    assert len(shots) == 1 and shots[0].framing == "wide"


def test_effective_shots_synthesizes_single_when_empty():
    shots = effective_shots(_scene(duration_s=4, seed=3, voiceover="vo", caption="cap"))
    assert len(shots) == 1
    only = shots[0]
    assert only.framing == "" and only.duration_s == 4 and only.seed == 3
    assert only.voiceover == "vo" and only.caption == "cap"


def test_load_project_spec_parses_shots(tmp_path):
    f = tmp_path / "project.yaml"
    f.write_text(
        "project: p\nstyle: crochet\nscenes:\n"
        "  - id: s2\n    prompt: ciudad\n    duration_s: 5\n    shots:\n"
        "      - framing: wide\n        duration_s: 2\n"
        "      - framing: close\n        duration_s: 1.5\n        voiceover: hola\n",
        encoding="utf-8",
    )
    sc = load_project_spec(f).scenes[0]
    assert len(sc.shots) == 2 and sc.shots[1].voiceover == "hola"


# --- D-078: voiceover/caption de ESCENA caen al primer plano ------------------

def test_effective_shots_inherits_scene_voice_to_first_shot():
    """Antes morian en silencio con `shots:` declarados: video pagado, voz que
    nunca sonaba (y el advisory daba falso negativo)."""
    from pipeline.contracts import Shot

    s = _scene(voiceover="hola mundo", caption="EL CAPTION",
               shots=[Shot(action="a", duration_s=2), Shot(action="b", duration_s=3)])
    shots = effective_shots(s)
    assert shots[0].voiceover == "hola mundo"
    assert shots[0].caption == "EL CAPTION"
    assert shots[1].voiceover is None
    assert s.shots[0].voiceover is None  # NO muta el spec en disco


def test_effective_shots_respects_shot_level_voice():
    from pipeline.contracts import Shot

    s = _scene(voiceover="voz de escena",
               shots=[Shot(action="a", duration_s=2),
                      Shot(action="b", duration_s=2, voiceover="voz de plano")])
    shots = effective_shots(s)
    assert shots[0].voiceover is None       # un plano YA declara voz: la escena no pisa
    assert shots[1].voiceover == "voz de plano"
