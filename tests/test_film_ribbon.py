"""Core: cinta de planos pixel-real (D-059).

Separación imagen-clave vs frame condicionante: el keyframe (nivel escena, lo que
se ve en el storyboard) es el frame-DESTINO del plano, no el frame-0. La cinta
aplana (escena, plano) en orden y encadena: cada plano encadenado arranca del
último frame REAL del clip anterior (extraído por ffmpeg) y aterriza en su
destino (Kling start→end). La `transition` gobierna: cut/smash_cut/wipe rompen
la cadena (un corte ES un corte); match_cut/dissolve/continuo encadenan.

Lógica pura (sin red ni ffmpeg real) -> core (CLAUDE.md).
"""

from pathlib import Path

from pipeline.assemble import last_frame_cmd
from pipeline.contracts import Scene, Shot
from pipeline.project import ProjectSpec
from pipeline.providers.fal_kling import video_arguments
from pipeline.runner import _video_inputs, chain_continues, plan_ribbon
from pipeline.strategies.common import scene_to_request


# --- chain_continues: la transition gobierna el encadenado ------------------

def test_chain_breaks_on_hard_transitions():
    for t in ("cut", "smash_cut", "wipe"):
        assert chain_continues(t) is False


def test_chain_continues_on_soft_or_none():
    for t in ("match_cut", "dissolve", None):
        assert chain_continues(t) is True


# --- plan_ribbon: aplanado (escena, plano) en orden + estado de cadena ------

def _spec() -> ProjectSpec:
    return ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=4, shots=[
            Shot(action="x", duration_s=2, transition="match_cut"),
            Shot(action="y", duration_s=2, transition="cut"),
        ]),
        Scene(id="s2", prompt="b", duration_s=2, shots=[
            Shot(action="z", duration_s=2, transition="dissolve"),
        ]),
        Scene(id="s3", prompt="c", duration_s=2),  # sin shots -> 1 plano implícito
    ])


def test_ribbon_flattens_shots_in_order_with_ids():
    ribbon = plan_ribbon(_spec())
    assert [e["shot_id"] for e in ribbon] == ["s1", "s1.2", "s2", "s3"]
    assert [e["scene"].id for e in ribbon] == ["s1", "s1", "s2", "s3"]


def test_ribbon_chain_state_crosses_scenes_and_breaks_on_cut():
    ribbon = plan_ribbon(_spec())
    by_id = {e["shot_id"]: e["chained"] for e in ribbon}
    assert by_id["s1"] is False      # primer plano del film: sin cadena
    assert by_id["s1.2"] is True     # s1 -> match_cut -> encadena
    assert by_id["s2"] is False      # s1.2 -> cut -> rompe (cruce de escena con corte)
    assert by_id["s3"] is True       # s2 -> dissolve -> encadena CRUZANDO la escena


# --- scene_to_request: start->end cuando hay frame de cinta -----------------

def test_request_interpolates_start_to_destino_when_chained():
    scene = Scene(id="s1", prompt="p", duration_s=2,
                  keyframe=Path("destino.png"), start_frame=Path("prev_last.png"))
    req = scene_to_request(scene)
    assert req.init_image == Path("prev_last.png")   # arranca donde terminó el anterior
    assert req.end_image == Path("destino.png")      # aterriza en la imagen-clave


def test_request_falls_back_to_destino_as_init_when_not_chained():
    scene = Scene(id="s1", prompt="p", duration_s=2, keyframe=Path("destino.png"))
    req = scene_to_request(scene)
    assert req.init_image == Path("destino.png")     # comportamiento actual (corte)
    assert req.end_image is None


# --- fal_kling: end_image_url en los argumentos ------------------------------

def test_video_arguments_include_end_image_url():
    args = video_arguments("prompt", seed=7, init_url="http://a/i.png",
                           end_url="http://a/e.png")
    assert args["image_url"] == "http://a/i.png"
    assert args["end_image_url"] == "http://a/e.png"
    assert args["seed"] == 7


def test_video_arguments_omit_end_when_absent():
    args = video_arguments("prompt", seed=None, init_url="http://a/i.png", end_url=None)
    assert "end_image_url" not in args and "seed" not in args


# --- cache: la cadena entra a la key del video (cascada D-059) ---------------

def test_video_inputs_chain_key_changes_cache_identity():
    base = dict(keyframe_key="kf", strategy="router", provider_sig={"kling": "m"},
                scene_prompt="p", duration_s=2.0, aspect="9:16", seed=0)
    a = _video_inputs(**base, chain_from=None)
    b = _video_inputs(**base, chain_from="prev_vid_key")
    assert a != b  # cambiar el plano upstream invalida este (cascada)


# --- ffmpeg: comando del último frame (pura) ----------------------------------

def test_last_frame_cmd_seeks_from_end():
    cmd = last_frame_cmd(Path("clip.mp4"), Path("out.png"))
    assert "-sseof" in cmd and "clip.mp4" in cmd and "out.png" in cmd
    assert "-frames:v" in cmd and cmd[cmd.index("-frames:v") + 1] == "1"
