"""Core: animatic de poses frontera + interpolación paralela (D-060, revisa D-059).

Cada plano queda definido por DOS poses generadas: el start-still (derivado por
edición del destino del plano anterior — continuidad de elementos a través de
todo el film, incluso en cortes) y el DESTINO (el keyframe elegido/encadenado:
donde el clip aterriza). El video es puro intercalado start→destino (Kling
end_image_url) y corre EN PARALELO (vuelve D-039). El trim conserva el
ATERRIZAJE (recorta la cabeza, no la cola — el hallazgo del A/B D-060).

Lógica pura (sin red ni ffmpeg real) -> core (CLAUDE.md).
"""

from pathlib import Path

from pipeline.assemble import tail_start
from pipeline.contracts import Scene, Shot
from pipeline.project import ProjectSpec
from pipeline.prompt_compile import compose_start_pose_prompt
from pipeline.providers.fal_kling import video_arguments
from pipeline.runner import _video_inputs, plan_ribbon
from pipeline.strategies.common import scene_to_request


# --- plan_ribbon: aplanado (escena, plano) en orden --------------------------

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


def test_ribbon_carries_incoming_transition():
    # La transición de ENTRADA al plano = la transición del plano anterior;
    # alimenta el prompt del start-still (cómo se reencuadra). Primer plano: None.
    ribbon = plan_ribbon(_spec())
    by_id = {e["shot_id"]: e["transition_in"] for e in ribbon}
    assert by_id["s1"] is None
    assert by_id["s1.2"] == "match_cut"
    assert by_id["s2"] == "cut"        # cruza la escena llevando la transición
    assert by_id["s3"] == "dissolve"


# --- start-still: el prompt de la pose de apertura (pura) --------------------

def test_start_pose_prompt_describes_opening_not_peak():
    shot = Shot(action="he extends his open palm fully", duration_s=3)
    p = compose_start_pose_prompt(shot, transition_in="match_cut")
    assert "he extends his open palm fully" in p
    assert "beginning" in p.lower() or "opening" in p.lower()


def test_start_pose_prompt_reframes_freely_on_hard_cuts():
    shot = Shot(action="x", duration_s=2)
    hard = compose_start_pose_prompt(shot, transition_in="cut")
    soft = compose_start_pose_prompt(shot, transition_in="dissolve")
    assert hard != soft  # la transición de entrada cambia la instrucción de reencuadre


# --- scene_to_request: start->destino (contrato D-059, intacto en D-060) -----

def test_request_interpolates_start_to_destino():
    scene = Scene(id="s1", prompt="p", duration_s=2,
                  keyframe=Path("destino.png"), start_frame=Path("start_pose.png"))
    req = scene_to_request(scene)
    assert req.init_image == Path("start_pose.png")
    assert req.end_image == Path("destino.png")


def test_request_falls_back_to_destino_as_init_without_start():
    scene = Scene(id="s1", prompt="p", duration_s=2, keyframe=Path("destino.png"))
    req = scene_to_request(scene)
    assert req.init_image == Path("destino.png")
    assert req.end_image is None


# --- fal_kling: el end-frame REAL (D-070 corrige D-059) ------------------------

def test_video_arguments_include_tail_image_url():
    """`tail_image_url` es el nombre real en Kling 2.1 PRO; `end_image_url` no
    existía en ningún endpoint y fal lo ignoraba en silencio (D-070)."""
    args = video_arguments("prompt", seed=7, init_url="http://a/i.png",
                           end_url="http://a/e.png")
    assert args["image_url"] == "http://a/i.png"
    assert args["tail_image_url"] == "http://a/e.png"


# --- cache: el start-still entra a la key del video ---------------------------

def test_video_inputs_start_key_changes_cache_identity():
    base = dict(keyframe_key="kf", strategy="router", provider_sig={"kling": "m"},
                scene_prompt="p", duration_s=2.0, aspect="9:16", seed=0)
    a = _video_inputs(**base, chain_from="start_key_1")
    b = _video_inputs(**base, chain_from="start_key_2")
    assert a != b  # otra pose de apertura = otro clip


# --- trim: conservar el ATERRIZAJE (recorte de cabeza, D-060) -----------------

def test_tail_start_keeps_the_landing():
    assert tail_start(5.0, 3.0) == 2.0   # corta los primeros 2s, conserva el final
    assert tail_start(5.0, 5.0) == 0.0
    assert tail_start(3.0, 5.0) == 0.0   # clip más corto que lo pedido: no recorta
