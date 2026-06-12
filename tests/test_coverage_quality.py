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
