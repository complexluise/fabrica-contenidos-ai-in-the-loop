"""Core Sprint 6.5: nombres semánticos legibles (D-026).

Test-first. Solo la lógica pura (slugify, readable_name, fallback de
semantic_slug); la derivación con Claude Haiku es I/O y se valida con smoke.
"""

from pipeline.naming import readable_name, semantic_slug, slugify


def test_slugify_basic():
    assert slugify("Plano general de una ciudad LEGO al amanecer") == "plano_general_de_una"


def test_slugify_strips_accents_and_symbols():
    assert slugify("Acción épica: ¡el héroe!") == "accion_epica_el_heroe"


def test_slugify_empty_falls_back():
    assert slugify("...!!!") == "scene"


def test_slugify_respects_max_words():
    assert slugify("uno dos tres cuatro cinco seis", max_words=2) == "uno_dos"


def test_readable_name_format():
    assert readable_name("s1", "ciudad_lego", 0, ".png") == "s1_ciudad_lego_0.png"
    assert readable_name("juan", "cara", 3, ".png") == "juan_cara_3.png"


def test_semantic_slug_falls_back_without_llm(monkeypatch):
    # Sin LLM (no key / falla) -> usa slugify del texto.
    monkeypatch.setattr("pipeline.naming._slug_via_llm", lambda text: None)
    assert semantic_slug("Una ciudad LEGO al amanecer") == "una_ciudad_lego_al"


def test_semantic_slug_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr("pipeline.naming._slug_via_llm", lambda text: "heroe_epico")
    assert semantic_slug("lo que sea") == "heroe_epico"
