"""Core Sprint 2: Cascade, Ensemble y dispatcher híbrido.

Test-first. Fakes async (sin red): un FakeProvider genera un clip con su costo,
un FakeGate decide pasa/score por provider. Verifican la LÓGICA que decide
costo y calidad — el corazón del ahorro multi-modelo.
"""

from pathlib import Path

import pytest

from pipeline.config import load_routing
from pipeline.contracts import GateReport, GenResult, SceneRequirements, ShotJob
from pipeline.gate import gate_score
from pipeline.strategies.cascade import Cascade
from pipeline.strategies.ensemble import Ensemble
from pipeline.strategies.dispatch import build_strategy, select_rule
from pipeline.strategies.router import SmartRouter


class FakeProvider:
    def __init__(self, name, cost, caps):
        self.name = name
        self.cost_per_second = cost
        self.capabilities = set(caps)
        self.model = f"m/{name}"

    def supports(self, required):
        return required.issubset(self.capabilities)

    def estimate_cost(self, d):
        return self.cost_per_second * d

    async def generate(self, req):
        return GenResult(
            video_path=Path(f"{self.name}.mp4"), provider=self.name,
            cost_usd=self.cost_per_second * req.duration_s, latency_s=1.0,
        )


class FakeGate:
    """Pasa si el score del provider >= 0.7."""

    def __init__(self, scores):
        self.scores = scores

    async def evaluate(self, job, result):
        s = self.scores.get(result.provider, 0.0)
        return GateReport(passed=s >= 0.7, aesthetic=s, char_consistency=s, clip_adherence=s)


def _job(req=None):
    return ShotJob(id="s", prompt="p", duration_s=4, requirements=req or SceneRequirements())


# --- gate_score -------------------------------------------------------------

def test_gate_score_monotonic_and_penalizes_artifacts():
    low = GateReport(passed=True, aesthetic=0.5, char_consistency=0.5, clip_adherence=0.5)
    high = GateReport(passed=True, aesthetic=0.9, char_consistency=0.9, clip_adherence=0.9)
    dirty = GateReport(passed=True, aesthetic=0.9, char_consistency=0.9, clip_adherence=0.9, artifacts=0.8)
    assert gate_score(high) > gate_score(low)
    assert gate_score(dirty) < gate_score(high)


# --- T2.2 Cascade -----------------------------------------------------------

async def test_cascade_stops_at_first_passing_tier():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.4, "seedance": 0.9})  # kling falla, seedance pasa
    res = await Cascade().run(_job(), providers, gate)
    assert res.provider == "seedance"
    assert res.raw_meta["gate_passed"] is True
    assert res.raw_meta["tiers_tried"] == ["kling", "seedance"]


async def test_cascade_accumulates_cost_of_failed_tiers():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.4, "seedance": 0.9})
    res = await Cascade().run(_job(), providers, gate)
    # paga ambos: 0.03*4 + 0.06*4 = 0.36
    assert res.cost_usd == pytest.approx(0.36)


async def test_cascade_first_tier_passes_no_escalation():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.9})
    res = await Cascade().run(_job(), providers, gate)
    assert res.provider == "kling"
    assert res.cost_usd == pytest.approx(0.12)  # solo kling


async def test_cascade_all_fail_marks_human_queue():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.2, "seedance": 0.3})
    res = await Cascade().run(_job(), providers, gate)
    assert res.raw_meta["gate_passed"] is False
    assert res.raw_meta["needs_human"] is True


# --- T2.3 Ensemble ----------------------------------------------------------

async def test_ensemble_picks_highest_score():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("veo", 0.5, {"i2v"}),
                 FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.75, "veo": 0.95, "seedance": 0.8})
    res = await Ensemble().run(_job(), providers, gate)
    assert res.provider == "veo"  # mejor score


async def test_ensemble_cost_is_sum_of_all_candidates():
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("seedance", 0.06, {"i2v"})]
    gate = FakeGate({"kling": 0.8, "seedance": 0.9})
    res = await Ensemble().run(_job(), providers, gate)
    assert res.cost_usd == pytest.approx(0.36)  # 0.12 + 0.24


class BoomProvider(FakeProvider):
    async def generate(self, req):
        raise RuntimeError("proveedor caido")


async def test_ensemble_tolerates_a_failing_provider():
    # Veo falla (sin key), pero kling/seedance sí: la escena no debe morir.
    providers = [BoomProvider("veo", 0.5, {"i2v"}), FakeProvider("kling", 0.03, {"i2v"})]
    gate = FakeGate({"kling": 0.8})
    res = await Ensemble().run(_job(), providers, gate)
    assert res.provider == "kling"


async def test_ensemble_raises_when_all_providers_fail():
    providers = [BoomProvider("veo", 0.5, {"i2v"}), BoomProvider("kling", 0.03, {"i2v"})]
    with pytest.raises(Exception):
        await Ensemble().run(_job(), providers, FakeGate({}))


async def test_ensemble_filters_by_capability():
    # Escena con audio: solo veo lo soporta -> ensemble corre solo veo.
    providers = [FakeProvider("kling", 0.03, {"i2v"}), FakeProvider("veo", 0.5, {"i2v", "audio"})]
    gate = FakeGate({"veo": 0.9})
    res = await Ensemble().run(_job(SceneRequirements(needs_audio=True)), providers, gate)
    assert res.provider == "veo"


# --- T2.4 Dispatcher híbrido ------------------------------------------------

def test_select_rule_maps_class_to_strategy():
    routing = load_routing(Path("config") / "routing.yaml", profile="prod")
    assert select_rule("hero", routing).strategy == "ensemble"
    assert select_rule("standard", routing).strategy == "router"
    assert select_rule("volume", routing).strategy == "cascade"


def test_select_rule_providers_from_yaml():
    routing = load_routing(Path("config") / "routing.yaml", profile="prod")
    assert select_rule("hero", routing).providers == ["veo", "seedance", "kling"]


def test_build_strategy_returns_named_instance():
    assert build_strategy("cascade").name == "cascade"
    assert build_strategy("ensemble").name == "ensemble"
    assert build_strategy("router").name == "router"


# --- D-076: el router acumula el costo de los reintentos -----------------------

async def test_router_retry_accumulates_cost():
    """El reintento por gate tambien se pago: cost_usd = suma de intentos
    (antes el router descartaba el costo del intento fallido; cascade/ensemble
    ya acumulaban — la telemetria subreportaba)."""
    providers = [FakeProvider("kling", 0.03, {"i2v"})]
    gate = FakeGate({"kling": 0.0})  # nunca pasa -> 1 reintento (max_retries=1)
    res = await SmartRouter(max_retries=1).run(_job(), providers, gate)
    assert res.raw_meta["attempts"] == 2
    assert res.cost_usd == pytest.approx(0.24)  # 2 intentos x 0.03 x 4s


async def test_router_single_attempt_cost_unchanged():
    providers = [FakeProvider("kling", 0.03, {"i2v"})]
    gate = FakeGate({"kling": 0.9})  # pasa a la primera
    res = await SmartRouter(max_retries=1).run(_job(), providers, gate)
    assert res.raw_meta["attempts"] == 1
    assert res.cost_usd == pytest.approx(0.12)
