"""Core: contrato guion->spec - voz que suena + routing satisfacible (D-057).

Cierra el hueco del ciclo (auditoria de `esquiva_conversemos`): el TTS solo lee
`voiceover` (no `dialogue`), y `needs_audio` exige una capability que ningun provider
de video tiene -> rompe el routing. Se cubre con visibilidad (advisories de firma) +
guard temprano (preflight en run_project, simetrico al casting D-056).

Logica pura/config (sin red ni ffmpeg) -> core (CLAUDE.md).
"""

import pytest

from pipeline.config import (
    Config,
    KeyframeConfig,
    ProviderConfig,
    RoutingConfig,
    StrategyRule,
    StyleConfig,
)
from pipeline.contracts import Scene, SceneRequirements, Shot
from pipeline.project import Project, ProjectSpec
from pipeline.runner import run_project
from pipeline.state import signing_advisories
from pipeline.strategies.dispatch import routing_gaps


def _routing(rules=None) -> RoutingConfig:
    rules = rules or {"standard": StrategyRule(strategy="router", providers=["kling"])}
    return RoutingConfig(rules=rules, thresholds={})


def _providers(caps_by_name: dict) -> dict:
    return {
        n: ProviderConfig(name=n, backend="fal", model=f"m/{n}", cost_per_second=0.0,
                          capabilities=set(caps))
        for n, caps in caps_by_name.items()
    }


# --- routing_gaps (pura) ----------------------------------------------------

def test_routing_gaps_flags_unsatisfiable_audio():
    routing = _routing({"standard": StrategyRule(strategy="router", providers=["kling"])})
    providers = _providers({"kling": {"i2v", "lipsync"}})  # ningun provider con audio
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2,
              requirements=SceneRequirements(needs_audio=True)),
    ])
    gaps = routing_gaps(spec, routing, providers)
    assert len(gaps) == 1
    assert gaps[0]["scene"] == "s1"
    assert "audio" in gaps[0]["missing"]


def test_routing_gaps_empty_when_satisfiable():
    routing = _routing()
    providers = _providers({"kling": {"i2v", "lipsync"}})
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2),  # solo i2v
    ])
    assert routing_gaps(spec, routing, providers) == []


def test_routing_gaps_unknown_class_falls_back_to_standard_providers():
    # clase fuera del perfil -> cae a standard (D-055) y usa SUS providers para el chequeo
    routing = _routing({"standard": StrategyRule(strategy="router", providers=["kling"])})
    providers = _providers({"kling": {"i2v"}})
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2, **{"class": "hero"},
              requirements=SceneRequirements(needs_audio=True)),
    ])
    gaps = routing_gaps(spec, routing, providers)
    assert gaps and gaps[0]["scene"] == "s1"


# --- signing_advisories: dialogue_no_voice + unroutable ---------------------

def test_signing_advisories_dialogue_no_voice():
    routing = _routing()
    providers = _providers({"kling": {"i2v"}})
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2, dialogue="Juan: hola",
              shots=[Shot(framing="x", duration_s=2)]),  # dialogue pero ningun voiceover
    ])
    kinds = {(a["scene"], a["kind"]) for a in signing_advisories(spec, routing, providers)}
    assert ("s1", "dialogue_no_voice") in kinds


def test_signing_advisories_dialogue_with_voiceover_is_clean():
    routing = _routing()
    providers = _providers({"kling": {"i2v"}})
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2, dialogue="Juan: hola",
              shots=[Shot(framing="x", duration_s=2, voiceover="hola")]),
    ])
    kinds = {a["kind"] for a in signing_advisories(spec, routing, providers)}
    assert "dialogue_no_voice" not in kinds


def test_signing_advisories_unroutable_audio():
    routing = _routing()
    providers = _providers({"kling": {"i2v", "lipsync"}})  # sin audio
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2,
              requirements=SceneRequirements(needs_audio=True),
              shots=[Shot(framing="x", duration_s=2, voiceover="hola")]),
    ])
    kinds = {(a["scene"], a["kind"]) for a in signing_advisories(spec, routing, providers)}
    assert ("s1", "unroutable") in kinds


# --- preflight en run_project (guard temprano, simetrico a D-056) -----------

def _cfg(caps_by_name: dict, rules=None) -> Config:
    style = StyleConfig(style="lego", keyframe=KeyframeConfig(backend="fal", model="m/kf"),
                        prompt_template="{scene_prompt}")
    return Config(providers=_providers(caps_by_name), routing=_routing(rules), style=style)


async def test_run_project_preflight_raises_on_unroutable(tmp_path):
    proj = Project(slug="t", root=tmp_path)
    proj.dir.mkdir(parents=True)
    cfg = _cfg({"kling": {"i2v", "lipsync"}})  # sin audio
    spec = ProjectSpec(slug="t", style="lego", format="9:16", scenes=[
        Scene(id="s1", prompt="p", duration_s=2,
              requirements=SceneRequirements(needs_audio=True)),
    ])
    # Falla temprano (antes de construir providers o gastar), nombrando la capability.
    with pytest.raises(RuntimeError, match="audio"):
        await run_project(proj, spec, cfg)
