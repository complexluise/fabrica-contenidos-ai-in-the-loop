"""Core: integridad de selecciones/casting + validacion al firmar + costo (D-055).

Cubre el endurecimiento del flujo de keyframes/UI (feedback-keyframes-ui.md):
- T5/T14: detectar selecciones que apuntan a frames borrados; render falla claro.
- T9: (re)elegir el ancla invalida los previews encadenados de planos 2+.
- T3: descartar un candidato reconcilia la seleccion por path.
- T7/T13: avisos no bloqueantes al firmar (clase desconocida, escena sin planos).
- T11: marcar el origen (upload vs IA).
- T15: costo estimado de generar candidatos.

Logica pura/disco (sin red ni ffmpeg) -> es core testeable (CLAUDE.md).
"""

import logging
from pathlib import Path

import pytest
import yaml

from pipeline.config import ProviderConfig, RoutingConfig, StrategyRule
from pipeline.contracts import Scene, Shot
from pipeline.project import Character, Project, ProjectSpec, relativize
from pipeline.state import estimate_image_cost, signing_advisories
from pipeline.strategies.dispatch import select_rule
from pipeline.studio import (
    delete_candidate,
    invalidate_shot_previews,
    is_upload,
    record_picks,
    render,
    verify_casting,
    verify_selections,
)


def _project(tmp_path: Path) -> Project:
    proj = Project(slug="t", root=tmp_path)
    (proj.cache_dir / "keyframes").mkdir(parents=True)
    return proj


def _img(proj: Project, name: str) -> Path:
    p = proj.cache_dir / "keyframes" / name
    p.write_bytes(b"\x89PNG")
    return p


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# --- T5/T14: verificacion de selecciones rotas -----------------------------

def test_verify_selections_flags_missing_files(tmp_path):
    proj = _project(tmp_path)
    _img(proj, "a.png")  # existe
    _write(proj.selections_path, {
        "s1": "cache/keyframes/a.png",       # ok
        "s2": "cache/keyframes/gone.png",    # borrado
    })
    assert verify_selections(proj) == ["s2"]


def test_verify_selections_empty_when_all_present(tmp_path):
    proj = _project(tmp_path)
    _img(proj, "a.png")
    _write(proj.selections_path, {"s1": "cache/keyframes/a.png"})
    assert verify_selections(proj) == []


def test_verify_casting_flags_missing_faces(tmp_path):
    proj = _project(tmp_path)
    (proj.cache_dir / "cast").mkdir(parents=True)
    face = proj.cache_dir / "cast" / "juan.png"
    face.write_bytes(b"x")
    _write(proj.dir / "casting.yaml", {
        "juan": "cache/cast/juan.png",   # ok
        "ana": "cache/cast/missing.png",  # borrada
    })
    assert verify_casting(proj) == ["ana"]


async def test_render_raises_on_broken_selection(tmp_path):
    proj = _project(tmp_path)
    _write(proj.selections_path, {"s1": "cache/keyframes/gone.png"})
    spec = ProjectSpec(slug="t", style="lego", format="9:16",
                       scenes=[Scene(id="s1", prompt="p", duration_s=2)])
    # cfg no se toca antes de la validacion (run_project nunca se llama).
    with pytest.raises(RuntimeError, match="ya no está en disco"):
        await render(proj, spec, None)


async def test_render_raises_on_broken_casting(tmp_path):
    # D-056: hueco simetrico de D-055. La seleccion de keyframe esta OK en disco,
    # pero la cara de casting de un personaje referenciado apunta a un archivo
    # borrado (residuo de fork/rename, cache limpiada). render() debe fallar claro
    # y temprano, no dejar que el provider reviente subiendo un init_image fantasma.
    proj = _project(tmp_path)
    a = _img(proj, "a.png")  # keyframe valido -> pasa el chequeo de selections
    _write(proj.selections_path, {"s1": relativize(proj.dir, a)})
    _write(proj.dir / "casting.yaml", {"Presentador": "cache/cast/missing.png"})
    spec = ProjectSpec(
        slug="t", style="lego", format="9:16",
        characters={"Presentador": Character(
            name="Presentador", refs=[Path("cache/cast/missing.png")])},
        scenes=[Scene(id="s1", prompt="p", duration_s=2, characters=["Presentador"])],
    )
    with pytest.raises(RuntimeError, match="cara elegida"):
        await render(proj, spec, None)


async def test_render_ignores_broken_casting_of_unused_character(tmp_path):
    # No bloquear por una entrada de casting vieja de un personaje que ninguna escena
    # del render usa: solo importan las caras que el render realmente va a subir.
    proj = _project(tmp_path)
    a = _img(proj, "a.png")
    _write(proj.selections_path, {"s1": relativize(proj.dir, a)})
    _write(proj.dir / "casting.yaml", {"Viejo": "cache/cast/missing.png"})
    spec = ProjectSpec(
        slug="t", style="lego", format="9:16",
        scenes=[Scene(id="s1", prompt="p", duration_s=2)],  # no referencia a "Viejo"
    )
    # cfg=None: si la validacion no bloquea, run_project se invoca y revienta con
    # AttributeError sobre None -> prueba que pasamos la validacion de casting.
    with pytest.raises(Exception) as exc:
        await render(proj, spec, None)
    assert "cara elegida" not in str(exc.value)


# --- T9: invalidar previews al reelegir el ancla ---------------------------

def test_record_picks_invalidates_shot_previews(tmp_path):
    proj = _project(tmp_path)
    a, b = _img(proj, "a.png"), _img(proj, "b.png")
    _write(proj.candidates_path, {"s1": [str(a), str(b)]})
    _write(proj.dir / "shot_previews.yaml", {"s1": ["old1", "old2"], "s2": ["x"]})

    record_picks(proj, {"s1": 1})

    previews = yaml.safe_load((proj.dir / "shot_previews.yaml").read_text(encoding="utf-8"))
    assert "s1" not in previews   # ancla reelegido -> previews viejos descartados
    assert "s2" in previews        # otra escena no se toca
    selections = yaml.safe_load(proj.selections_path.read_text(encoding="utf-8"))
    assert selections["s1"] == relativize(proj.dir, b)


def test_invalidate_shot_previews_noop_without_file(tmp_path):
    proj = _project(tmp_path)
    assert invalidate_shot_previews(proj, ["s1"]) == []


# --- T3: descartar un candidato --------------------------------------------

def test_delete_candidate_drops_selection_when_it_pointed_there(tmp_path):
    proj = _project(tmp_path)
    a, b = _img(proj, "a.png"), _img(proj, "b.png")
    _write(proj.candidates_path, {"s1": [str(a), str(b)]})
    _write(proj.selections_path, {"s1": relativize(proj.dir, a)})  # elegido el idx 0

    res = delete_candidate(proj, "s1", 0)

    assert res["remaining"] == 1
    assert res["selection_dropped"] is True
    manifest = yaml.safe_load(proj.candidates_path.read_text(encoding="utf-8"))
    assert manifest["s1"] == [str(b)]
    selections = yaml.safe_load(proj.selections_path.read_text(encoding="utf-8")) or {}
    assert "s1" not in selections


def test_delete_candidate_keeps_unrelated_selection(tmp_path):
    proj = _project(tmp_path)
    a, b = _img(proj, "a.png"), _img(proj, "b.png")
    _write(proj.candidates_path, {"s1": [str(a), str(b)]})
    _write(proj.selections_path, {"s1": relativize(proj.dir, b)})  # elegido el idx 1

    res = delete_candidate(proj, "s1", 0)  # borro el idx 0 (no elegido)

    assert res["selection_dropped"] is False
    selections = yaml.safe_load(proj.selections_path.read_text(encoding="utf-8"))
    assert selections["s1"] == relativize(proj.dir, b)


def test_delete_candidate_rejects_out_of_range(tmp_path):
    proj = _project(tmp_path)
    a = _img(proj, "a.png")
    _write(proj.candidates_path, {"s1": [str(a)]})
    with pytest.raises(ValueError):
        delete_candidate(proj, "s1", 5)


# --- T11: origen del candidato ---------------------------------------------

def test_is_upload_detects_human_uploads():
    assert is_upload("cache/keyframes/upload_abc123.png") is True
    assert is_upload(Path("/x/cache/keyframes/upload_abc.jpg")) is True
    assert is_upload("cache/keyframes/deadbeef.png") is False


# --- T7/T13: avisos al firmar ----------------------------------------------

def test_signing_advisories_flags_empty_shots_and_unknown_class():
    # T7 real: la clase es valida en el contrato (Literal hero/standard/volume) pero
    # el PERFIL activo puede no definirla -> cae a 'standard' sin avisar. Aca el perfil
    # solo define standard/volume, asi que una escena 'hero' es "desconocida".
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2),  # sin shots
        Scene(id="s2", prompt="p", duration_s=2, **{"class": "standard"},
              shots=[Shot(framing="x", duration_s=2)]),
        Scene(id="s3", prompt="p", duration_s=2, **{"class": "hero"},
              shots=[Shot(framing="x", duration_s=2)]),  # no esta en el perfil
    ])
    routing = RoutingConfig(rules={
        "standard": StrategyRule(strategy="router", providers=["k"]),
        "volume": StrategyRule(strategy="cascade", providers=["k"]),
    }, thresholds={})
    providers = {"k": ProviderConfig(name="k", backend="fal", model="m",
                                     cost_per_second=0.0, capabilities={"i2v"})}
    adv = signing_advisories(spec, routing, providers)
    kinds = {(a["scene"], a["kind"]) for a in adv}
    assert ("s1", "no_shots") in kinds
    assert ("s3", "unknown_class") in kinds
    assert ("s2", "unknown_class") not in kinds  # standard esta en el perfil
    assert ("s2", "no_shots") not in kinds        # s2 tiene plano


def test_signing_advisories_clean_spec_has_none():
    # "Limpio" también para D-062 (bloque completo) y D-072 (el plano de video
    # declara su frase de movimiento — sin `motion` hay aviso de tweening).
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=5,
              shots=[Shot(framing="x", duration_s=5,
                          motion="he nods slowly, then holds")]),
    ])
    routing = RoutingConfig(rules={
        "standard": StrategyRule(strategy="router", providers=["k"]),
    }, thresholds={})
    providers = {"k": ProviderConfig(name="k", backend="fal", model="m",
                                     cost_per_second=0.0, capabilities={"i2v"})}
    assert signing_advisories(spec, routing, providers) == []


# --- T7: dispatch avisa cuando cae a standard ------------------------------

def test_select_rule_warns_on_unknown_class(caplog):
    routing = RoutingConfig(
        rules={"standard": StrategyRule(strategy="router", providers=["kling"])},
        thresholds={},
    )
    with caplog.at_level(logging.WARNING):
        rule = select_rule("epic", routing)
    assert rule.strategy == "router"  # cae a standard
    assert any("epic" in r.message for r in caplog.records)


def test_select_rule_no_warning_on_known_class(caplog):
    routing = RoutingConfig(
        rules={"hero": StrategyRule(strategy="ensemble", providers=["veo"]),
               "standard": StrategyRule(strategy="router", providers=["kling"])},
        thresholds={},
    )
    with caplog.at_level(logging.WARNING):
        rule = select_rule("hero", routing)
    assert rule.strategy == "ensemble"
    assert not caplog.records


# --- T15: costo estimado ----------------------------------------------------

def test_estimate_image_cost():
    assert estimate_image_cost(12, 4, 0.003) == pytest.approx(0.144)
    assert estimate_image_cost(0, 4, 0.003) == 0.0
    assert estimate_image_cost(3, 0, 0.003) == 0.0


# --- D-078: "mas encuadres" jamas reusa un seed emitido ------------------------

def test_candidate_seed_offset_monotonic():
    from pipeline.studio import candidate_seed_offset

    assert candidate_seed_offset(None, 0) == 0
    assert candidate_seed_offset(None, 3) == 3   # compat: proyectos sin contador
    assert candidate_seed_offset(5, 3) == 5      # borraste candidatos: NO vuelve el descartado
    assert candidate_seed_offset(2, 4) == 4


# --- D-078: la biblia del mundo viaja al checkpoint interactivo ----------------

async def test_gen_keyframes_scene_carries_world(tmp_path, monkeypatch):
    """El runner generaba destinos CON world (D-067); el studio generaba los
    candidatos SIN el -> el humano curaba anclas sin el set canonico."""
    from pipeline.config import Config, KeyframeConfig, StyleConfig

    proj = _project(tmp_path)
    img = tmp_path / "gen.png"
    img.write_bytes(b"png")

    class _FakeKF:
        seen: dict = {}

        def __init__(self, *a, **kw):
            pass

        async def generate(self, scene, ref_images=None, seed=None, framing="",
                           world=None, ref_map=None):
            _FakeKF.seen = {"world": world, "ref_map": ref_map}
            return img

    monkeypatch.setattr("pipeline.studio.KeyframeGenerator", _FakeKF)
    routing = RoutingConfig(rules={"standard": StrategyRule(strategy="router", providers=["k"])},
                            thresholds={})
    cfg = Config(
        providers={"k": ProviderConfig(name="k", backend="fal", model="m",
                                       cost_per_second=0.0, capabilities={"i2v"})},
        routing=routing,
        style=StyleConfig(style="lego", keyframe=KeyframeConfig(backend="fal", model="kf"),
                          prompt_template="{scene_prompt}"),
    )
    spec = ProjectSpec(slug="t", style="lego", format="9:16",
                       world="LEGO megacity at dusk",
                       scenes=[Scene(id="s1", prompt="p", duration_s=4)])
    from pipeline.studio import gen_keyframes_scene
    await gen_keyframes_scene(proj, spec, cfg, "s1", n=1)
    assert _FakeKF.seen["world"] == "LEGO megacity at dusk"
