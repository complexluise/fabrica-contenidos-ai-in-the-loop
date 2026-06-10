"""Core: prompt derivado de la narrativa (D-046).

La llamada real a Haiku (`compile_prompt` con key) es smoke (D-012). Aqui solo la
logica pura: el hash narrativo, el estado stale/manual, el brief fuente, el
fallback deterministico y el round-trip de los campos nuevos en el spec.
"""

from pipeline.contracts import Scene
from pipeline.project import (
    Character,
    CharacterDesign,
    ProjectSpec,
    load_project_spec,
    write_spec,
)
from pipeline.prompt_compile import (
    _deterministic_prompt,
    mark_synced,
    narrative_brief,
)


def _scene(**kw) -> Scene:
    base = dict(id="s1", prompt="ciudad LEGO al amanecer", duration_s=5)
    base.update(kw)
    return Scene(**base)


# --- narrative_hash ---------------------------------------------------------

def test_narrative_hash_estable_para_misma_narrativa():
    a = _scene(beat="apertura", ambience="tráfico", dialogue="Ana: hola", characters=["ana"])
    b = _scene(beat="apertura", ambience="tráfico", dialogue="Ana: hola", characters=["ana"])
    assert a.narrative_hash() == b.narrative_hash()


def test_narrative_hash_cambia_con_cada_campo():
    base = _scene(beat="apertura", ambience="tráfico", dialogue="hola", characters=["ana"])
    h = base.narrative_hash()
    assert _scene(beat="cierre", ambience="tráfico", dialogue="hola", characters=["ana"]).narrative_hash() != h
    assert _scene(beat="apertura", ambience="lluvia", dialogue="hola", characters=["ana"]).narrative_hash() != h
    assert _scene(beat="apertura", ambience="tráfico", dialogue="chau", characters=["ana"]).narrative_hash() != h
    assert _scene(beat="apertura", ambience="tráfico", dialogue="hola", characters=["bob"]).narrative_hash() != h


def test_narrative_hash_ignora_el_prompt_visual():
    # El prompt NO entra al hash: cambiarlo no marca la narrativa como distinta.
    a = _scene(beat="apertura", prompt="uno")
    b = _scene(beat="apertura", prompt="otro totalmente distinto")
    assert a.narrative_hash() == b.narrative_hash()


# --- prompt_stale / manual --------------------------------------------------

def test_prompt_stale_sin_hash_es_stale():
    assert _scene(beat="apertura").prompt_stale is True


def test_mark_synced_deja_en_sintonia():
    s = mark_synced(_scene(beat="apertura"))
    assert s.prompt_stale is False
    assert s.prompt_manual is False
    assert s.prompt_src_hash == s.narrative_hash()


def test_cambiar_narrativa_vuelve_stale():
    s = mark_synced(_scene(beat="apertura"))
    s.beat = "clímax"  # la narrativa cambió después de compilar
    assert s.prompt_stale is True


def test_manual_nunca_es_stale():
    s = _scene(beat="apertura", prompt_manual=True)
    assert s.prompt_stale is False  # aunque no haya hash
    s2 = mark_synced(_scene(beat="apertura"))
    s2.prompt_manual = True
    s2.beat = "otro"  # narrativa cambió, pero es manual -> no stale
    assert s2.prompt_stale is False


# --- narrative_brief / fallback ---------------------------------------------

def test_narrative_brief_incluye_campos_y_design():
    chars = {"ana": Character(name="ana", design=CharacterDesign(prompt="ingeniera de casco"))}
    s = _scene(beat="apertura", ambience="lluvia", dialogue="Ana: vamos", characters=["ana"])
    brief = narrative_brief(s, chars)
    assert "Beat: apertura" in brief
    assert "ana (ingeniera de casco)" in brief
    assert "lluvia" in brief
    assert "vamos" in brief


def test_narrative_brief_sin_narrativa():
    out = narrative_brief(Scene(id="s1", prompt="x", duration_s=3))
    assert "neutro" in out.lower()


def test_deterministic_prompt_concatena_narrativa():
    s = _scene(beat="apertura", ambience="lluvia", characters=["ana", "bob"])
    out = _deterministic_prompt(s)
    assert "apertura" in out and "ana, bob" in out and "lluvia" in out


def test_deterministic_prompt_cae_al_prompt_si_no_hay_narrativa():
    s = Scene(id="s1", prompt="ciudad LEGO", duration_s=3)
    assert _deterministic_prompt(s) == "ciudad LEGO"


# --- persistencia (round-trip de los campos nuevos) -------------------------

def test_round_trip_preserva_manual_y_hash(tmp_path):
    s = mark_synced(_scene(beat="apertura", ambience="lluvia"))
    s.prompt_manual = True
    spec = ProjectSpec(slug="demo", style="lego", format="9:16", scenes=[s])
    out = write_spec(spec, tmp_path / "project.yaml")
    reloaded = load_project_spec(out)
    rs = reloaded.scenes[0]
    assert rs.prompt_manual is True
    assert rs.prompt_src_hash == s.prompt_src_hash


def test_round_trip_omite_defaults(tmp_path):
    # Escena sin compilar ni override: el YAML no ensucia con los campos nuevos.
    spec = ProjectSpec(slug="demo", style="lego", format="9:16", scenes=[_scene()])
    out = write_spec(spec, tmp_path / "project.yaml")
    text = out.read_text(encoding="utf-8")
    assert "prompt_manual" not in text
    assert "prompt_src_hash" not in text
