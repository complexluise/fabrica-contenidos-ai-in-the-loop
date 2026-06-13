"""Core: estado derivado del proyecto (D-032).

`compute_stage` es la maquina de estados pura (transiciones + guards);
`derive_state` lee los artefactos en disco. Ambas son fuente unica de verdad.
"""

import yaml

from pipeline.contracts import Scene
from pipeline.project import Character, CharacterDesign, Project, ProjectSpec
from pipeline.state import (
    CastingState, KeyframesState, Stage, compute_stage, derive_state,
)


def _cast(needed=0, chosen=0, cands=False):
    return CastingState(needed=needed, chosen=chosen, has_candidates=cands)


def _kf(total=1, chosen=0, cands=False):
    return KeyframesState(total=total, chosen=chosen, has_candidates=cands)


def _stage(**kw):
    base = dict(has_fal_key=True, storyboard_signed=True, casting=_cast(),
                keyframes=_kf(1, 1), render_done=True, export_done=True)
    base.update(kw)
    return compute_stage(**base)


# --- compute_stage: la maquina pura ----------------------------------------

def test_sin_claves_gana_a_todo():
    # aunque todo lo demas este hecho, sin FAL_KEY el primer paso son las claves
    assert _stage(has_fal_key=False) is Stage.SIN_CLAVES


def test_guion_antes_que_casting():
    # con claves pero sin storyboard firmado -> GUION (antes que casting/encuadres)
    assert _stage(storyboard_signed=False) is Stage.GUION


def test_casting_antes_que_encuadres():
    assert _stage(casting=_cast(needed=1, chosen=0), keyframes=_kf(1, 0),
                  render_done=False, export_done=False) is Stage.CASTING


def test_encuadres_cuando_faltan_picks():
    assert _stage(keyframes=_kf(2, 1), render_done=False, export_done=False) is Stage.ENCUADRES


def test_guard_render_necesita_encuadres_completos():
    # encuadres completos pero sin render -> RENDER (nunca salta a PAQUETE)
    assert _stage(render_done=False, export_done=False) is Stage.RENDER


def test_paquete_despues_de_render():
    assert _stage(export_done=False) is Stage.PAQUETE


def test_completo_cuando_no_queda_nada():
    assert _stage() is Stage.COMPLETO


def test_sin_personajes_se_salta_casting():
    # needed=0 -> CASTING no aplica, va directo a ENCUADRES
    assert _stage(casting=_cast(needed=0), keyframes=_kf(1, 0),
                  render_done=False, export_done=False) is Stage.ENCUADRES


# --- derive_state: lectura de disco ----------------------------------------

def _spec(scenes, characters=None):
    return ProjectSpec(slug="t", style="lego", format="9:16",
                       scenes=scenes, characters=characters or {})


def _project(tmp_path):
    proj = Project(slug="t", root=tmp_path)
    proj.dir.mkdir(parents=True)
    return proj


def _sign(proj):
    """Crea el marcador storyboard.signed para habilitar los pasos siguientes."""
    (proj.dir / "storyboard.signed").write_text("", encoding="utf-8")


def test_derive_sin_firmar_pide_guion(tmp_path):
    proj = _project(tmp_path)
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.stage is Stage.GUION
    assert st.storyboard_signed is False


def test_derive_proyecto_firmado_pide_encuadres(tmp_path):
    proj = _project(tmp_path)
    _sign(proj)
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.stage is Stage.ENCUADRES
    assert st.keyframes.total == 1 and st.keyframes.chosen == 0


def test_derive_cuenta_selecciones(tmp_path):
    proj = _project(tmp_path)
    _sign(proj)
    # La selección apunta a un archivo project-relative que EXISTE en disco (D-044).
    kf = proj.dir / "k.png"
    kf.write_bytes(b"img")
    proj.selections_path.write_text(yaml.safe_dump({"s1": "k.png"}), encoding="utf-8")
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.keyframes.chosen == 1
    assert st.stage is Stage.RENDER  # elegido, pero sin run todavia


def test_derive_no_cuenta_seleccion_con_archivo_ausente(tmp_path):
    # Proyecto importado de otra máquina: la clave está pero el frame no existe ->
    # NO cuenta como elegido (D-044). Evita el "el estado cree que está y no está".
    proj = _project(tmp_path)
    _sign(proj)
    proj.selections_path.write_text(yaml.safe_dump({"s1": "no/existe.png"}), encoding="utf-8")
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.keyframes.chosen == 0
    assert st.stage is Stage.ENCUADRES


def test_derive_casting_pendiente(tmp_path):
    proj = _project(tmp_path)
    _sign(proj)
    juan = Character(name="juan", design=CharacterDesign(prompt="cara LEGO de juan"))
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)], {"juan": juan})
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.casting.needed == 1 and st.casting.chosen == 0
    assert st.stage is Stage.CASTING


def test_derive_sin_clave_es_sin_claves(tmp_path):
    proj = _project(tmp_path)
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    assert derive_state(proj, spec, has_fal_key=False).stage is Stage.SIN_CLAVES


# --- D-078: un run FALLIDO no es un render hecho ------------------------------

def test_derive_render_ignora_run_sin_final(tmp_path):
    proj = _project(tmp_path)
    _sign(proj)
    kf = proj.dir / "k.png"
    kf.write_bytes(b"img")
    proj.selections_path.write_text(yaml.safe_dump({"s1": "k.png"}), encoding="utf-8")
    (proj.runs_dir / "20260612-000000-dead").mkdir(parents=True)  # run que reviento a mitad
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.render.done is False
    assert st.stage is Stage.RENDER  # el estado NO miente (D-032)


def test_derive_render_hecho_con_final(tmp_path):
    proj = _project(tmp_path)
    _sign(proj)
    kf = proj.dir / "k.png"
    kf.write_bytes(b"img")
    proj.selections_path.write_text(yaml.safe_dump({"s1": "k.png"}), encoding="utf-8")
    run_dir = proj.runs_dir / "20260612-000001-ok"
    run_dir.mkdir(parents=True)
    (run_dir / "final_9x16.mp4").write_bytes(b"v")
    spec = _spec([Scene(id="s1", prompt="x", duration_s=5)])
    st = derive_state(proj, spec, has_fal_key=True)
    assert st.render.done is True
    assert st.stage is Stage.PAQUETE


# --- D-082: huella del plan narrativo (que invalida la firma y que no) -------

def test_plan_fingerprint_ignores_prompt_and_framing():
    from pipeline.contracts import Shot
    from pipeline.state import plan_fingerprint

    a = [Scene(id="s1", prompt="ciudad", duration_s=4,
               shots=[Shot(framing="wide", duration_s=4)])]
    b = [Scene(id="s1", prompt="ciudad NEON", duration_s=4,
               shots=[Shot(framing="close", duration_s=4)])]
    assert plan_fingerprint(a) == plan_fingerprint(b)


def test_plan_fingerprint_changes_on_narrative_edit():
    from pipeline.contracts import Shot
    from pipeline.state import plan_fingerprint

    base = [Scene(id="s1", prompt="x", duration_s=4,
                  shots=[Shot(duration_s=4)])]
    dialogo = [Scene(id="s1", prompt="x", duration_s=4, dialogue="Juan: hola.",
                     shots=[Shot(duration_s=4)])]
    motor = [Scene(id="s1", prompt="x", duration_s=4,
                   shots=[Shot(duration_s=4, motion="the camera pushes in slowly")])]
    assert plan_fingerprint(base) != plan_fingerprint(dialogo)
    assert plan_fingerprint(base) != plan_fingerprint(motor)
