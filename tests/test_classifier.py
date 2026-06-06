"""Core: reglas del clasificador (lo determinista). El LLM arbitra solo lo gris."""

from pipeline.classifier import classify_by_rules
from pipeline.contracts import Scene, SceneRequirements


def _scene(**kw) -> Scene:
    base = dict(id="s", prompt="una toma", duration_s=4)
    base.update(kw)
    return Scene(**base)


def test_dialogue_is_hero():
    assert classify_by_rules(_scene(dialogue="hola")) == "hero"


def test_needs_audio_is_hero():
    s = _scene(requirements=SceneRequirements(needs_audio=True))
    assert classify_by_rules(s) == "hero"


def test_multiple_characters_is_standard():
    assert classify_by_rules(_scene(characters=["a", "b"])) == "standard"


def test_no_characters_is_volume():
    assert classify_by_rules(_scene(characters=[])) == "volume"


def test_broll_hint_is_volume():
    s = _scene(prompt="establishing shot de la ciudad", characters=["a"])
    assert classify_by_rules(s) == "volume"


def test_single_character_plain_is_ambiguous():
    # Un personaje, sin pistas -> None (lo decide el LLM).
    assert classify_by_rules(_scene(prompt="primer plano", characters=["a"])) is None
