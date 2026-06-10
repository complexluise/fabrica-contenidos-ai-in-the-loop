"""Core: autoría asistida (Fase 2 app, T2.1) + escritura del spec (T2.2).

Test-first del parseo del borrador del LLM (`author.parse_draft`), del round-trip
del escritor del spec (`project.write_spec`) y del guard de selecciones (D-022).
La llamada real a Claude (`draft_project`) se valida con smoke, no acá.
"""

from pathlib import Path

import pytest

from pipeline.author import ProjectDraft, parse_draft
from pipeline.ingest import extract_text
from pipeline.project import load_project_spec, spec_from_dict, write_spec


# --- T2.1: parse_draft (parseo del JSON del LLM) ---------------------------

_GOOD = """Claro, aquí tienes el borrador:
{
  "title": "Ciudad que despierta",
  "brief": "Una ciudad LEGO arranca su día.",
  "scenes": [
    {"id": "s1", "prompt": "ciudad LEGO al amanecer", "duration_s": 5,
     "beat": "apertura", "characters": [],
     "shots": [{"framing": "plano general", "duration_s": 5, "caption": "Amanece"}]}
  ]
}
Listo.
"""


def test_parse_draft_extracts_title_and_scenes():
    draft = parse_draft(_GOOD)
    assert draft.title == "Ciudad que despierta"
    assert draft.brief.startswith("Una ciudad LEGO")
    assert len(draft.scenes) == 1
    assert draft.scenes[0].id == "s1"
    assert draft.scenes[0].shots[0].caption == "Amanece"


def test_parse_draft_assigns_missing_ids():
    draft = parse_draft('{"title": "X", "scenes": [{"prompt": "a", "duration_s": 4}, {"prompt": "b", "duration_s": 4}]}')
    assert [s.id for s in draft.scenes] == ["s1", "s2"]


def test_parse_draft_derives_duration_from_shots_when_missing():
    draft = parse_draft(
        '{"title": "X", "scenes": [{"id": "s1", "prompt": "a", '
        '"shots": [{"framing": "f1", "duration_s": 3}, {"framing": "f2", "duration_s": 2}]}]}'
    )
    assert draft.scenes[0].duration_s == 5


def test_parse_draft_defaults_style_and_format():
    draft = parse_draft('{"title": "X", "scenes": [{"id": "s1", "prompt": "a", "duration_s": 4}]}')
    assert draft.style == "lego"
    assert draft.format == "9:16"


def test_parse_draft_raises_without_json():
    with pytest.raises(ValueError):
        parse_draft("no hay json aquí")


def test_draft_to_spec_carries_fields():
    draft = parse_draft(_GOOD)
    spec = draft.to_spec("ciudad")
    assert spec.slug == "ciudad"
    assert spec.title == "Ciudad que despierta"
    assert len(spec.scenes) == 1


# --- D-047: artefacto audiovisual enriquecido ------------------------------

_ARTIFACT = """{
  "title": "Pozo", "scenes": [{
    "id": "s1", "prompt": "telescopio de acero", "visual_intensity": 4,
    "shots": [{
      "intention": "revelar la estructura", "action": "manos deslizan tres tubos",
      "duration_s": 3,
      "camera": {"size": "LS", "angle": "overhead", "move": "push_in", "focus": "deep"},
      "visual": {"tone": "neutral", "palette": ["plata", "crema"], "focal_point": "el centro",
                 "graphics": "ACERO + CEMENTO = el sello"},
      "transition": "match_cut", "voiceover": "Un pozo no es un tubo."
    }]
  }]
}"""


def test_parse_draft_enriched_shot_artifact():
    s = parse_draft(_ARTIFACT).scenes[0]
    assert s.visual_intensity == 4
    sh = s.shots[0]
    assert sh.intention == "revelar la estructura"
    assert sh.action == "manos deslizan tres tubos"
    assert sh.camera.size == "LS" and sh.camera.angle == "overhead" and sh.camera.move == "push_in"
    assert sh.visual.tone == "neutral" and sh.visual.palette == ["plata", "crema"]
    assert sh.transition == "match_cut"


def test_parse_draft_drops_invalid_camera_enum_without_crashing():
    raw = ('{"title": "X", "scenes": [{"id": "s1", "prompt": "a", "duration_s": 3, '
           '"shots": [{"action": "algo", "duration_s": 3, '
           '"camera": {"size": "wide-ish", "angle": "overhead"}, "transition": "fancy"}]}]}')
    sh = parse_draft(raw).scenes[0].shots[0]
    assert sh.camera.size == "MS"  # 'wide-ish' invalido -> default
    assert sh.camera.angle == "overhead"  # valido se conserva
    assert sh.transition is None  # 'fancy' invalido -> descartado


def test_parse_draft_clamps_visual_intensity():
    raw = ('{"title": "X", "scenes": [{"id": "s1", "prompt": "a", "duration_s": 3, '
           '"visual_intensity": 9, "shots": [{"action": "x", "duration_s": 3}]}]}')
    assert parse_draft(raw).scenes[0].visual_intensity == 5


# --- ingest.extract_text ---------------------------------------------------

def test_extract_text_reads_md(tmp_path):
    p = tmp_path / "guion.md"
    p.write_text("# Hola\nTexto", encoding="utf-8")
    assert "Hola" in extract_text(p)


def test_extract_text_rejects_unknown_suffix(tmp_path):
    p = tmp_path / "guion.pdf"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_text(p)


# --- T2.2: write_spec (round-trip + idempotencia) --------------------------

def _spec(tmp_path):
    spec_file = tmp_path / "src.yaml"
    spec_file.write_text(
        "project: demo\ntitle: Demo\nbrief: Una prueba\nstyle: lego\nformat: '9:16'\n"
        "characters:\n  juan:\n    design:\n      prompt: minifigura con barba\n"
        "      refs: [data/juan.jpg]\n"
        "scenes:\n"
        "  - id: s1\n    prompt: ciudad LEGO\n    duration_s: 5\n    beat: apertura\n"
        "    characters: [juan]\n    caption: Hola\n"
        "    shots:\n      - framing: plano general\n        duration_s: 5\n"
        "  - id: s2\n    prompt: plaza LEGO\n    duration_s: 4\n",
        encoding="utf-8",
    )
    return load_project_spec(spec_file)


def test_write_spec_round_trips(tmp_path):
    spec = _spec(tmp_path)
    out = write_spec(spec, tmp_path / "out" / "project.yaml")
    reloaded = load_project_spec(out)
    assert reloaded == spec


def test_write_spec_is_idempotent(tmp_path):
    spec = _spec(tmp_path)
    a = write_spec(spec, tmp_path / "a.yaml").read_text(encoding="utf-8")
    reloaded = load_project_spec(tmp_path / "a.yaml")
    b = write_spec(reloaded, tmp_path / "b.yaml").read_text(encoding="utf-8")
    assert a == b


def test_write_spec_omits_empty_fields(tmp_path):
    draft = ProjectDraft(title="X", scenes=parse_draft(_GOOD).scenes)
    out = write_spec(draft.to_spec("x"), tmp_path / "p.yaml")
    text = out.read_text(encoding="utf-8")
    assert "music" not in text  # no se escribe lo vacío
    assert "voice_id" not in text


def test_spec_from_dict_url_slug_wins(tmp_path):
    spec = spec_from_dict({"project": "ignorado", "scenes": [{"id": "s1", "prompt": "a", "duration_s": 4}]}, "demo")
    assert spec.slug == "ignorado"  # el dict gana si lo trae
    spec2 = spec_from_dict({"scenes": [{"id": "s1", "prompt": "a", "duration_s": 4}]}, "demo")
    assert spec2.slug == "demo"  # sin 'project' usa el default


def test_spec_from_dict_rejects_invalid_scene():
    with pytest.raises(Exception):
        spec_from_dict({"scenes": [{"id": "s1", "prompt": "a", "duration_s": -1}]}, "demo")


# --- #8: personajes con design: auto en el borrador --------------------------

_CHARS = ('{"title": "X", "characters": {"juan": {"design": "obrero con casco amarillo"}, '
          '"ana": {"design": "ingeniera"}}, "scenes": [{"id": "s1", "prompt": "a", '
          '"duration_s": 4, "characters": ["juan"]}]}')


def test_parse_draft_parses_characters_with_design():
    d = parse_draft(_CHARS)
    assert set(d.characters) == {"juan", "ana"}
    assert d.characters["juan"].design.prompt == "obrero con casco amarillo"
    assert d.characters["juan"].design.refs == []  # el humano sube refs luego


def test_parse_draft_character_design_object_form():
    d = parse_draft('{"title": "X", "characters": {"juan": {"design": {"prompt": "obrero"}}}, '
                    '"scenes": [{"id": "s1", "prompt": "a", "duration_s": 4}]}')
    assert d.characters["juan"].design.prompt == "obrero"


def test_parse_draft_no_characters_ok():
    d = parse_draft('{"title": "X", "scenes": [{"id": "s1", "prompt": "a", "duration_s": 4}]}')
    assert d.characters == {}


def test_draft_to_spec_carries_characters():
    spec = parse_draft(_CHARS).to_spec("x")
    assert "juan" in spec.characters and spec.characters["juan"].design is not None


def test_write_spec_round_trips_characters(tmp_path):
    spec = parse_draft(_CHARS).to_spec("x")
    out = write_spec(spec, tmp_path / "p.yaml")
    reloaded = load_project_spec(out)
    assert reloaded.characters["juan"].design.prompt == "obrero con casco amarillo"
