"""Core: el motor que SÍ llega al servidor (D-070/D-071/D-072).

D-070 — "la cámara actúa": el hallazgo que lo cambió todo — fal IGNORA en
silencio los parámetros desconocidos. Kling 2.1 standard no tiene end-frame
(`end_image_url` nunca existió; en pro se llama `tail_image_url`), así que la
interpolación de D-059/D-060 jamás se ejecutó: pagamos i2v de deriva libre.
El paradigma nuevo: por defecto cada plano es i2v desde su DESTINO (el still
elegido) con la CÁMARA actuando (gramática brickfilm: el minifig posa, la
cámara actúa); `lands: true` declara los pocos planos que deben ATERRIZAR en
una pose — esos interpolan de verdad vía un provider con capability `end_frame`.

D-071 — 9:16 de punta a punta: los stills salían 1024x1024 (default Kontext),
el video 960x960 y el reframe recortaba ~44%% de cada composición. El formato
del spec viaja a la generación de imagen Y de video.

D-072 — el dialecto de movimiento: en i2v NO se re-describe la escena (la
imagen ES la escena). `shot.motion` es la frase de movimiento; el prompt de
video = instrucción de cámara + movimiento + endpoint. Sin `motion`, fallback
legacy (action) + advisory.

Lógica pura (sin red) -> core (CLAUDE.md).
"""

from pathlib import Path

from pipeline.config import ProviderConfig, RoutingConfig, StrategyRule, load_config
from pipeline.contracts import Camera, Scene, Shot
from pipeline.keyframe import image_size_args
from pipeline.project import Project, ProjectSpec
from pipeline.prompt_compile import compose_video_prompt, ensure_motion_endpoint
from pipeline.providers.fal_kling import video_arguments
from pipeline.runner import keyframe_inputs, pick_end_frame_provider
from pipeline.state import signing_advisories

CONFIG_DIR = Path("config")


# --- D-070: el parámetro REAL del end-frame -----------------------------------

def test_video_arguments_use_tail_image_url():
    """fal Kling 2.1 pro llama al end-frame `tail_image_url`. `end_image_url`
    no existe en NINGÚN endpoint 2.1 — fal lo ignoraba en silencio."""
    args = video_arguments("p", seed=7, init_url="http://a/i.png",
                           end_url="http://a/e.png")
    assert args["tail_image_url"] == "http://a/e.png"
    assert "end_image_url" not in args


def test_video_arguments_aspect_and_cfg():
    args = video_arguments("p", seed=None, init_url="u", end_url=None,
                           aspect="9:16", cfg_scale=0.7)
    assert args["aspect_ratio"] == "9:16"   # seedance lo honra; kling lo ignora (inocuo)
    assert args["cfg_scale"] == 0.7


def test_video_arguments_omit_optionals():
    args = video_arguments("p", seed=None, init_url="u", end_url=None)
    assert "tail_image_url" not in args and "cfg_scale" not in args


# --- D-070: lands es opt-in y enruta a un provider CAPAZ -----------------------

def _prov(name, cps, caps):
    return ProviderConfig(name=name, backend="fal", model=f"m/{name}",
                          cost_per_second=cps, capabilities=caps)


class _P:
    """Provider fake mínimo (forma del Protocol)."""
    def __init__(self, cfg):
        self.name, self.cost_per_second = cfg.name, cfg.cost_per_second
        self.capabilities = set(cfg.capabilities)


def test_pick_end_frame_provider_prefers_subset_then_cheapest_global():
    kling = _P(_prov("kling", 0.03, {"i2v"}))
    kling_pro = _P(_prov("kling_pro", 0.09, {"i2v", "end_frame"}))
    vidu = _P(_prov("vidu", 0.10, {"i2v", "end_frame"}))
    # en el subset del routing -> ese manda
    assert pick_end_frame_provider([kling_pro, kling], {"vidu": vidu}) is kling_pro
    # no está en el subset -> el más barato capaz de TODOS los configurados
    assert pick_end_frame_provider([kling], {"kling_pro": kling_pro, "vidu": vidu}) is kling_pro
    # nadie es capaz -> None (el plano degrada a cámara-actúa, con warning)
    assert pick_end_frame_provider([kling], {"kling": kling}) is None


def test_shot_lands_defaults_false():
    shot = Shot(action="x", duration_s=2)
    assert shot.lands is False and shot.media == "video" and shot.takes == 1


async def test_start_poses_only_for_lands_shots(tmp_path):
    """Las APERTURAS solo se generan para planos `lands` (los que interpolan):
    el resto arranca de su destino (cámara-actúa) — mitad de stills, cero
    poses fantasma que ningún video usa."""
    from types import SimpleNamespace
    from pipeline.runner import ensure_boundary_stills

    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=4, shots=[
            Shot(action="x", duration_s=2),                # cámara-actúa: sin apertura
            Shot(action="y", duration_s=2, lands=True),    # aterriza: apertura + destino
        ]),
    ])
    cfg = load_config(CONFIG_DIR, "lego")
    img = tmp_path / "gen.png"; img.write_bytes(b"\x89PNG")
    calls = []
    async def gen(scene, ref_images=None, seed=None, framing="", **kw):
        calls.append(framing)
        return img
    out = await ensure_boundary_stills(proj, spec, cfg, SimpleNamespace(generate=gen), {})

    starts = [f for f in calls if "OPENING" in f]
    assert len(starts) == 1                      # solo el plano lands
    assert out[0]["start"] is None and out[0]["start_key"] is None
    assert out[1]["start"] is not None and out[1]["start_key"] is not None


# --- D-071: el formato viaja a la generación de imagen -------------------------

def test_image_size_args_by_model_family():
    # familia flux clásica -> image_size enum
    assert image_size_args("fal-ai/flux-lora", "9:16") == {"image_size": "portrait_16_9"}
    assert image_size_args("fal-ai/flux-lora", "16:9") == {"image_size": "landscape_16_9"}
    # kontext / nano-banana -> aspect_ratio
    assert image_size_args("fal-ai/flux-pro/kontext/max/multi", "9:16") == {"aspect_ratio": "9:16"}
    assert image_size_args("fal-ai/nano-banana/edit", "9:16") == {"aspect_ratio": "9:16"}
    # formato desconocido -> sin args (no romper)
    assert image_size_args("fal-ai/flux-lora", "4:5") == {}


def test_keyframe_inputs_carry_aspect():
    """Cambiar el formato invalida el still (antes salían cuadrados para 9:16)."""
    cfg = load_config(CONFIG_DIR, "lego")
    a = keyframe_inputs("p", cfg, [], aspect="9:16")
    b = keyframe_inputs("p", cfg, [], aspect="1:1")
    assert a != b and a["aspect"] == "9:16"


# --- D-072: el dialecto de movimiento ------------------------------------------

def test_video_prompt_speaks_motion_not_scene():
    """Con `motion`, el prompt de video es cámara + movimiento + endpoint — la
    re-descripción de la escena (el `action` del still) NO viaja al video."""
    shot = Shot(action="Wide on the wet rooftop, two minifigures facing each other",
                motion="The agent jabs his pointing finger forward twice, quickly",
                duration_s=2, camera=Camera(move="push_in"))
    p = compose_video_prompt(shot)
    assert "wet rooftop" not in p                    # cero re-descripción
    assert p.startswith("Slow dolly in")             # cámara PRIMERO
    assert "jabs his pointing finger" in p
    assert "settle" in p.lower() or "hold" in p.lower()  # endpoint siempre


def test_video_prompt_static_camera_is_explicit():
    """Cámara sin especificar = deriva/morphing (documentado). `static` se dice."""
    shot = Shot(action="x", motion="he raises his open palm slowly", duration_s=2)
    p = compose_video_prompt(shot)
    assert "static" in p.lower() and "fixed" in p.lower()


def test_video_prompt_orbit_for_bullet_time():
    """D-070 (brickfilm): bullet-time = pose congelada + cámara orbitando."""
    shot = Shot(action="x", motion="raindrops hang motionless in the air",
                duration_s=2, camera=Camera(move="orbit"))
    p = compose_video_prompt(shot)
    assert "orbit" in p.lower()


def test_video_prompt_falls_back_to_action_without_motion():
    """Proyectos sin `motion` no rompen: fallback legacy (action+move)."""
    shot = Shot(action="he deflects the strike", duration_s=2,
                camera=Camera(move="track"))
    p = compose_video_prompt(shot)
    assert "he deflects the strike" in p


def test_ensure_motion_endpoint_appends_once():
    assert "settles" in ensure_motion_endpoint("he turns his head quickly")
    closed = "he turns, then stops facing the door"
    assert ensure_motion_endpoint(closed) == closed  # ya tiene endpoint


# --- D-072: advisories del dialecto y del routing lands ------------------------

def _routing():
    return RoutingConfig(rules={"standard": StrategyRule(strategy="router", providers=["k"]),
                                "hero": StrategyRule(strategy="router", providers=["k"])},
                         thresholds={})


def test_missing_motion_is_flagged():
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=4, shots=[
            Shot(action="a", duration_s=2),                         # sin motion -> aviso
            Shot(action="b", motion="he nods, then holds", duration_s=2),
        ]),
    ])
    provs = {"k": _prov("k", 0.0, {"i2v"})}
    kinds = {(a["scene"], a["kind"]) for a in signing_advisories(spec, _routing(), provs)}
    assert ("s1", "shot_missing_motion") in kinds


def test_lands_without_capable_provider_is_flagged():
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=4, shots=[
            Shot(action="a", duration_s=4, motion="m, then holds", lands=True),
        ]),
    ])
    no_cap = {"k": _prov("k", 0.0, {"i2v"})}
    kinds = {a["kind"] for a in signing_advisories(spec, _routing(), no_cap)}
    assert "lands_unroutable" in kinds
    with_cap = {"k": _prov("k", 0.0, {"i2v"}),
                "kp": _prov("kp", 0.09, {"i2v", "end_frame"})}
    kinds2 = {a["kind"] for a in signing_advisories(spec, _routing(), with_cap)}
    assert "lands_unroutable" not in kinds2


# --- D-070: kling_pro existe en la config con la capability ---------------------

def test_kling_pro_provider_configured_with_end_frame():
    cfg = load_config(CONFIG_DIR, "lego")
    pro = cfg.providers.get("kling_pro")
    assert pro is not None and "end_frame" in pro.capabilities
    assert "pro" in pro.model  # endpoint pro: el único 2.1 con tail_image_url


# --- round-trip del spec: los campos nuevos persisten --------------------------

def test_new_shot_fields_roundtrip_in_spec():
    from pipeline.project import spec_from_dict, spec_to_dict
    spec = spec_from_dict({"scenes": [{
        "id": "s1", "prompt": "p", "duration_s": 6,
        "shots": [
            {"action": "a", "motion": "he lunges quickly, then stops", "duration_s": 2,
             "lands": True, "takes": 3, "speed": 1.15, "cfg_scale": 0.7},
            {"action": "b", "duration_s": 4, "media": "still"},
        ],
    }]}, "t")
    sh = spec.scenes[0].shots
    assert sh[0].lands is True and sh[0].takes == 3 and sh[0].speed == 1.15
    assert sh[1].media == "still" and sh[1].lands is False
    d = spec_to_dict(spec)["scenes"][0]["shots"]
    assert d[0]["motion"].startswith("he lunges") and d[0]["lands"] is True
    assert d[0]["takes"] == 3 and d[0]["speed"] == 1.15 and d[0]["cfg_scale"] == 0.7
    assert d[1]["media"] == "still" and "lands" not in d[1]  # defaults no ensucian el YAML
