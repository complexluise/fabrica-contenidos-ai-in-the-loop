"""Core: gramática de cobertura (D-062) + palancas de calidad (D-063).

D-062 — los huecos del oficio que nadie avisaba: cobertura pobre en heros,
voz más larga que el plano (se corta a mitad de palabra), encuadres repetidos
en cortes consecutivos, y el hueco de plata (el proveedor factura bloques de
5s; un plano de 2s paga 5). Todo entra al canal de advisories (D-055/D-057).

D-063 — el storyboard backend puede subir la calidad de IMAGEN: `model` y
`ref_model` del preset pisan al estilo (la config `model` de D-053 estaba
muerta); preset `fal-max` (Kontext) para poses con identidad fuerte. Y las
poses del animatic se pueden ELEGIR entre variantes (pose_picks, mismo patrón
que el ancla elegida: la key cambia → la cascada de cache es correcta).
"""

from pathlib import Path

import yaml

from pipeline.config import ProviderConfig, RoutingConfig, StrategyRule, load_config
from pipeline.contracts import Camera, Scene, Shot
from pipeline.project import Project, ProjectSpec
from pipeline.state import billing_summary, signing_advisories
from pipeline.studio import animatic_strip, record_pose_pick

CONFIG_DIR = Path("config")


def _routing():
    return RoutingConfig(rules={"standard": StrategyRule(strategy="router", providers=["k"]),
                                "hero": StrategyRule(strategy="router", providers=["k"])},
                         thresholds={})


def _providers():
    return {"k": ProviderConfig(name="k", backend="fal", model="m", cost_per_second=0.0,
                                capabilities={"i2v"})}


def _adv(spec):
    return {(a["scene"], a["kind"]) for a in signing_advisories(spec, _routing(), _providers())}


# --- D-062: cobertura pobre en heros ----------------------------------------

def test_hero_with_few_shots_is_flagged():
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=5, **{"class": "hero"},
              shots=[Shot(action="x", duration_s=5)]),  # hero con 1 plano
        Scene(id="s2", prompt="p", duration_s=9, **{"class": "hero"},
              shots=[Shot(action="a", duration_s=3), Shot(action="b", duration_s=3),
                     Shot(action="c", duration_s=3)]),  # hero bien cubierto
    ])
    kinds = _adv(spec)
    assert ("s1", "hero_thin_coverage") in kinds
    assert ("s2", "hero_thin_coverage") not in kinds


# --- D-062: voz más larga que el plano (se cortaría a mitad de palabra) ------

def test_vo_too_long_is_flagged():
    long_line = " ".join(["palabra"] * 20)  # ~8s de locución en un plano de 2s
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2,
              shots=[Shot(action="x", duration_s=2, voiceover=long_line)]),
        Scene(id="s2", prompt="p", duration_s=4,
              shots=[Shot(action="x", duration_s=4, voiceover="Conversemos.")]),
    ])
    kinds = _adv(spec)
    assert ("s1", "vo_too_long") in kinds
    assert ("s2", "vo_too_long") not in kinds


# --- D-062: encuadre repetido en cortes consecutivos -------------------------

def test_repeated_framing_is_flagged_across_consecutive_shots():
    cam = Camera(size="CU", angle="low")
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=6, shots=[
            Shot(action="a", duration_s=3, camera=cam),
            Shot(action="b", duration_s=3, camera=Camera(size="CU", angle="low")),  # mismo encuadre
        ]),
    ])
    assert ("s1", "repeated_framing") in _adv(spec)


def test_repeated_default_cameras_do_not_spam():
    # Dos cámaras default seguidas (autor no especificó) no son un "error de oficio".
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=6, shots=[
            Shot(action="a", duration_s=3), Shot(action="b", duration_s=3),
        ]),
    ])
    assert ("s1", "repeated_framing") not in _adv(spec)


# --- D-062: el hueco de plata (bloques de facturación del proveedor) ---------

def test_short_shots_billing_is_flagged_per_scene():
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=4,
              shots=[Shot(action="a", duration_s=2), Shot(action="b", duration_s=2)]),
        Scene(id="s2", prompt="p", duration_s=5, shots=[Shot(action="c", duration_s=5)]),
    ])
    kinds = _adv(spec)
    assert ("s1", "short_shot_billing") in kinds   # 2 planos de 2s pagan 10s
    assert ("s2", "short_shot_billing") not in kinds  # 5s = el bloque completo


def test_billing_summary_paid_vs_used():
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=4,
              shots=[Shot(action="a", duration_s=2), Shot(action="b", duration_s=7)]),
    ])
    b = billing_summary(spec, block_s=5.0)
    assert b["used_s"] == 9.0
    assert b["paid_s"] == 15.0  # 2s -> bloque de 5; 7s -> 2 bloques de 5


# --- D-063: el preset de storyboard pisa model/ref_model del estilo ----------

def test_storyboard_backend_overrides_image_models():
    cfg = load_config(CONFIG_DIR, "lego", backend="fal-max")
    assert "kontext" in (cfg.style.keyframe.ref_model or "")  # calidad de identidad
    cfg_base = load_config(CONFIG_DIR, "lego", backend="fal")
    assert "nano-banana" in (cfg_base.style.keyframe.ref_model or "")  # el barato sigue default


# --- D-063: elegir una variante de pose cambia la KEY (cascada correcta) -----

async def test_pose_pick_changes_key_and_path(tmp_path):
    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    variant = proj.cache_dir / "keyframes" / "variante_elegida.png"
    variant.write_bytes(b"\x89PNG")
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=3, shots=[Shot(action="x", duration_s=3)]),
    ])
    cfg = load_config(CONFIG_DIR, "lego")

    record_pose_pick(proj, "s1", "start", variant)  # persiste relativo (D-044)
    picks = yaml.safe_load((proj.dir / "pose_picks.yaml").read_text(encoding="utf-8"))
    assert picks["s1/start"] == "cache/keyframes/variante_elegida.png"

    strip = await animatic_strip(proj, spec, cfg)
    s1 = strip[0]
    assert s1["start"].endswith("variante_elegida.png")   # la pose elegida manda
    assert s1["start_key"].startswith("picked:")          # key distinta -> el clip aguas abajo se invalida


# --- D-063: las KEYS de la cadena son estables ante fallos de generación -----

async def test_chain_keys_stable_when_a_pose_generation_fails(tmp_path, monkeypatch):
    """Un fallo de generación a mitad del film NO corre las keys aguas abajo:
    la identidad es pura/posicional. Si no, lo generado queda bajo keys
    inalcanzables y los re-runs regeneran (plata) o pierden poses."""
    from unittest.mock import AsyncMock
    from pipeline.runner import ensure_boundary_stills

    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=3, shots=[Shot(action="x", duration_s=3)]),
        Scene(id="s2", prompt="b", duration_s=3, shots=[Shot(action="y", duration_s=3)]),
    ])
    cfg = load_config(CONFIG_DIR, "lego")

    img = tmp_path / "gen.png"
    img.write_bytes(b"\x89PNG")
    ok = AsyncMock(return_value=img)

    # Run A: todo genera OK -> keys de referencia.
    from types import SimpleNamespace
    kf_ok = SimpleNamespace(generate=ok)
    ref = await ensure_boundary_stills(proj, spec, cfg, kf_ok, {})
    ref_keys = [(b["kf_key"], b["start_key"]) for b in ref]

    # Run B (cache limpio): el PRIMER destino falla; el resto genera.
    import shutil
    shutil.rmtree(proj.cache_dir / "keyframes"); (proj.cache_dir / "keyframes").mkdir()
    calls = {"n": 0}
    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("proveedor caído")
        return img
    kf_flaky = SimpleNamespace(generate=flaky)
    out = await ensure_boundary_stills(proj, spec, cfg, kf_flaky, {})

    assert [(b["kf_key"], b["start_key"]) for b in out] == ref_keys  # keys idénticas
    assert out[0]["destino"] is None      # el fallo se refleja en el ARCHIVO, no en la key
    assert out[1]["destino"] is not None  # el resto siguió


# --- D-064: subtítulos estilo Instagram (envoltura pura) ----------------------

def test_wrap_caption_breaks_long_lines():
    from pipeline.post import wrap_caption
    t = wrap_caption("Detengamos la violencia. Conversemos ahora mismo.", width=18)
    lines = t.split("\n")
    assert len(lines) >= 2
    assert all(len(l) <= 22 for l in lines)  # ancho de lectura en vertical


def test_wrap_caption_caps_lines():
    from pipeline.post import wrap_caption
    t = wrap_caption(" ".join(["palabra"] * 30), width=18, max_lines=3)
    assert len(t.split("\n")) <= 3 and t.endswith("…")


def test_caption_filter_is_ig_style():
    from pipeline.post import caption_filter
    f = caption_filter(Path("cap.txt"), height=1920)
    assert "textfile=" in f          # newlines/acentos sin escaping frágil
    assert "borderw=" in f           # borde grueso, no cajita negra
    assert "box=1" not in f
    assert "0.72" in f or "0.70" in f  # zona segura sobre la UI de IG


# --- D-064: el ANCLA de la escena entra como base de TODAS sus poses ----------

async def test_scene_anchor_feeds_every_pose_of_the_scene(tmp_path):
    """Coherencia extrema (D-064): el ancla de la escena entra como referencia en
    TODAS sus poses — incluso el destino del plano 3 (que encadena del 2, no del
    ancla) y la apertura de una escena cuyo start deriva de la escena ANTERIOR."""
    from unittest.mock import AsyncMock
    from pipeline.runner import ensure_boundary_stills

    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    a1 = proj.cache_dir / "keyframes" / "ancla1.png"; a1.write_bytes(b"\x89PNG")
    a2 = proj.cache_dir / "keyframes" / "ancla2.png"; a2.write_bytes(b"\x89PNG")
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="a", duration_s=12, shots=[
            Shot(action="x", duration_s=4), Shot(action="y", duration_s=4),
            Shot(action="z", duration_s=4),
        ]),
        Scene(id="s2", prompt="b", duration_s=4, shots=[Shot(action="w", duration_s=4)]),
    ])
    cfg = load_config(CONFIG_DIR, "lego")
    img = tmp_path / "gen.png"; img.write_bytes(b"\x89PNG")
    calls = []
    async def gen(scene, ref_images=None, seed=None, framing="", **kw):
        calls.append((scene.id, framing, set(map(str, ref_images or []))))
        return img
    from types import SimpleNamespace
    kf = SimpleNamespace(generate=gen)

    await ensure_boundary_stills(proj, spec, cfg, kf, {"s1": a1, "s2": a2})

    # destino del plano 3 de s1 (encadena del plano 2): DEBE llevar el ancla a1
    d3 = [refs for sid, fr, refs in calls if sid == "s1" and "OPENING" not in fr]
    assert d3 and all(str(a1) in refs for refs in d3), d3
    # la apertura de s2 deriva del destino de s1, pero DEBE llevar el ancla a2
    s2_starts = [refs for sid, fr, refs in calls if sid == "s2" and "OPENING" in fr]
    assert s2_starts and all(str(a2) in refs for refs in s2_starts), s2_starts


# --- D-065: voz por PLANO (dos hablantes en una escena) -----------------------

def test_shot_voice_id_roundtrips_in_spec():
    from pipeline.project import spec_from_dict, spec_to_dict
    spec = spec_from_dict({"scenes": [{
        "id": "s1", "prompt": "p", "duration_s": 8,
        "voice_id": "voz_cepeda",
        "shots": [
            {"action": "a", "duration_s": 4, "voiceover": "¡Peleá!", "voice_id": "voz_espriella"},
            {"action": "b", "duration_s": 4, "voiceover": "Me defiendo."},
        ],
    }]}, "t")
    sh = spec.scenes[0].shots
    assert sh[0].voice_id == "voz_espriella" and sh[1].voice_id is None
    d = spec_to_dict(spec)["scenes"][0]["shots"]
    assert d[0]["voice_id"] == "voz_espriella" and "voice_id" not in d[1]


def test_voice_resolution_prefers_shot_over_scene():
    from pipeline.audio import resolve_voice
    from pipeline.runner import effective_voice
    scene = Scene(id="s1", prompt="p", duration_s=8, voice_id="voz_escena", shots=[
        Shot(action="a", duration_s=4, voice_id="voz_plano"),
        Shot(action="b", duration_s=4),
    ])
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[scene],
                       voice_id="voz_proyecto")
    assert effective_voice(scene, scene.shots[0]) == "voz_plano"   # el plano manda
    assert effective_voice(scene, scene.shots[1]) == "voz_escena"  # cae a la escena
    plano = scene.model_copy(update={"voice_id": effective_voice(scene, scene.shots[1])})
    assert resolve_voice(plano, spec) == "voz_escena"


# --- D-067: contexto canónico — el mundo, el estilo y las refs CON NOMBRE -----

def test_world_bible_roundtrips_and_feeds_styled_prompt():
    from pipeline.project import spec_from_dict, spec_to_dict
    from pipeline.keyframe import build_styled_prompt
    spec = spec_from_dict({
        "world": "one rain-soaked LEGO rooftop, green Matrix code glow in every puddle",
        "scenes": [{"id": "s1", "prompt": "the duel", "duration_s": 5}],
    }, "t")
    assert "rain-soaked" in spec.world
    assert spec_to_dict(spec)["world"].startswith("one rain-soaked")
    cfg = load_config(CONFIG_DIR, "lego")
    styled = build_styled_prompt(spec.scenes[0], cfg.style, "wide shot", world=spec.world)
    assert "rain-soaked" in styled and "the duel" in styled  # el mundo viaja a CADA prompt


def test_ref_map_names_every_reference():
    from pipeline.prompt_compile import compose_ref_map
    m = compose_ref_map(source_label="the previous moment of this film",
                        characters=["Cepeda", "Espriella"])
    assert "image 1" in m and "previous moment" in m
    assert "image 2" in m and "Cepeda" in m and "EXACT face" in m
    assert "image 3" in m and "Espriella" in m


def test_video_prompt_carries_style_and_world():
    from pipeline.keyframe import build_styled_prompt
    cfg = load_config(CONFIG_DIR, "lego")
    scene = Scene(id="s1", prompt="he deflects the strike", duration_s=4)
    styled = build_styled_prompt(scene, cfg.style, "fast deflection", world="LEGO rooftop in rain")
    # el prompt de VIDEO ahora pasa por el MISMO template de estilo que las imágenes
    assert "LEGO" in styled and "rooftop in rain" in styled


def test_kling_receives_negative_prompt():
    from pipeline.providers.fal_kling import video_arguments
    args = video_arguments("p", seed=None, init_url="u", end_url=None,
                           negative="blurry, morphing, extra limbs")
    assert args["negative_prompt"] == "blurry, morphing, extra limbs"
