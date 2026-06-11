"""Core: el artefacto de storyboard elevado (D-047).

Gramatica de camara (shot-list) + estructura visual (Bruce Block) -> texto de
encuadre componible. Aqui solo logica pura: el mapeo a lenguaje natural, los
defaults que se omiten, y el round-trip de los campos nuevos en el spec.
"""

from pipeline.contracts import Camera, Scene, Shot, Visual
from pipeline.project import (
    ProjectSpec,
    load_project_spec,
    write_spec,
)
from pipeline.prompt_compile import (
    camera_phrase,
    compose_keyframe_prompt,
    compose_video_prompt,
    motion_phrase,
    visual_phrase,
)


# --- camera_phrase (keyframe: SIN movimiento, D-048/A1) ---------------------

def test_camera_default_no_aporta_frase():
    assert camera_phrase(Camera()) == ""
    assert Camera().is_default() is True


def test_camera_phrase_traduce_vocabulario_sin_movimiento():
    cam = Camera(size="ECU", angle="overhead", move="push_in", focus="shallow")
    p = camera_phrase(cam)
    assert "extreme close-up" in p
    assert "overhead bird's-eye angle" in p
    assert "shallow depth of field" in p
    assert "push-in" not in p  # el movimiento NO va en el keyframe (imagen fija)


def test_camera_phrase_omite_foco_profundo_por_defecto():
    # focus=deep es el default -> no se menciona; lens opcional sí aparece.
    p = camera_phrase(Camera(size="CU", lens_mm=85))
    assert "deep focus" not in p
    assert "85mm lens" in p


# --- motion_phrase / compose_video_prompt (video: el movimiento) -----------

def test_motion_phrase_solo_movimiento():
    assert motion_phrase(Camera(move="static")) == ""
    assert "push-in" in motion_phrase(Camera(move="push_in"))
    assert "tracking" in motion_phrase(Camera(move="track"))


def test_compose_video_prompt_lleva_accion_y_movimiento():
    sh = Shot(action="manos deslizan los tubos", duration_s=3,
              camera=Camera(size="LS", angle="overhead", move="push_in"))
    out = compose_video_prompt(sh)
    assert "manos deslizan los tubos" in out
    assert "push-in" in out
    # el video NO re-describe la composicion fija (size/angle van al keyframe)
    assert "long shot" not in out


def test_compose_video_prompt_estatico_es_solo_accion():
    sh = Shot(action="la fibra se rompe", duration_s=2, camera=Camera(move="static"))
    assert compose_video_prompt(sh) == "la fibra se rompe"


# --- visual_phrase (Bruce Block) -------------------------------------------

def test_visual_vacio_no_aporta():
    assert visual_phrase(Visual()) == ""
    assert Visual().is_empty() is True


def test_visual_phrase_arma_dimensiones():
    vis = Visual(tone="low_key", palette=["cyan", "amber"],
                 foreground="manos", background="oscuridad",
                 focal_point="la grieta", graphics="ACERO + CEMENTO = el sello")
    p = visual_phrase(vis)
    assert "low-key lighting" in p
    assert "palette cyan, amber" in p
    assert "depth:" in p and "manos" in p and "oscuridad" in p
    assert "focal point on la grieta" in p
    assert 'on-screen graphics: "ACERO + CEMENTO = el sello"' in p


# --- compose_keyframe_prompt ----------------------------------------------------

def test_compose_usa_action_y_ensambla():
    sh = Shot(action="manos deslizan tres tubos concentricos", duration_s=3,
              camera=Camera(size="LS", angle="overhead"),
              visual=Visual(focal_point="el centro del telescopio"))
    out = compose_keyframe_prompt(sh)
    assert out.startswith("manos deslizan tres tubos concentricos")
    assert "long shot" in out
    assert "overhead bird's-eye angle" in out
    assert "focal point on el centro" in out


def test_compose_cae_a_framing_legacy_si_no_hay_action():
    sh = Shot(framing="overhead wide shot of the prop", duration_s=3)
    assert compose_keyframe_prompt(sh) == "overhead wide shot of the prop"


def test_compose_solo_action_sin_gramatica():
    sh = Shot(action="primer plano de la fibra rompiendose", duration_s=2)
    assert compose_keyframe_prompt(sh) == "primer plano de la fibra rompiendose"


# --- persistencia (round-trip del artefacto) --------------------------------

def test_round_trip_preserva_artefacto(tmp_path):
    sh = Shot(
        intention="revelar que el pozo no es un tubo simple",
        action="manos deslizan tres tubos plateados como un telescopio",
        duration_s=3,
        camera=Camera(size="LS", angle="overhead", move="push_in"),
        visual=Visual(tone="neutral", palette=["plata", "crema", "mostaza"],
                      focal_point="el centro", graphics="ACERO + CEMENTO = el sello"),
        transition="match_cut",
        voiceover="Un pozo no es un tubo.",
        sfx="click suave de tubos encajando",
    )
    scene = Scene(id="s1", prompt="x", duration_s=3, visual_intensity=4, shots=[sh])
    spec = ProjectSpec(slug="demo", style="crochet", format="9:16", scenes=[scene])
    out = write_spec(spec, tmp_path / "project.yaml")
    reloaded = load_project_spec(out)
    rsh = reloaded.scenes[0].shots[0]
    assert reloaded.scenes[0].visual_intensity == 4
    assert rsh.intention.startswith("revelar")
    assert rsh.action.startswith("manos deslizan")
    assert rsh.camera.size == "LS" and rsh.camera.angle == "overhead" and rsh.camera.move == "push_in"
    assert rsh.visual.tone == "neutral" and rsh.visual.palette == ["plata", "crema", "mostaza"]
    assert rsh.visual.graphics == "ACERO + CEMENTO = el sello"
    assert rsh.transition == "match_cut"


def test_round_trip_omite_defaults_del_artefacto(tmp_path):
    # Plano clasico (solo framing+audio): el YAML no se ensucia con camera/visual.
    sh = Shot(framing="plano general", duration_s=3, voiceover="hola")
    scene = Scene(id="s1", prompt="x", duration_s=3, shots=[sh])
    spec = ProjectSpec(slug="demo", style="lego", format="9:16", scenes=[scene])
    text = write_spec(spec, tmp_path / "project.yaml").read_text(encoding="utf-8")
    assert "camera:" not in text
    assert "visual:" not in text
    assert "intention:" not in text
    assert "visual_intensity" not in text
