"""L5 - Smart Cost Router.

En un solo paso, despacha la escena al provider MAS BARATO que cumple sus
requisitos. La logica de seleccion (`pick_provider`) es pura -> es core testeable
porque decide el costo de toda la produccion.
"""

from __future__ import annotations

from ..contracts import GenResult, QualityGate, Scene
from ..gate import report_scores
from ..providers.base import BaseProvider
from .common import eligible_providers, scene_to_request


def pick_provider(scene: Scene, providers: list[BaseProvider]) -> BaseProvider:
    """El mas barato que cumple las capabilities exigidas por la escena.

    Lanza si ningun provider cumple (mejor fallar fuerte que mandar a uno incapaz).
    """
    eligible = eligible_providers(scene, providers)
    if not eligible:
        required = scene.requirements.required_capabilities()
        raise ValueError(
            f"Ningun provider cumple {required or '{}'} para la escena {scene.id}. "
            f"Disponibles: {[(p.name, p.capabilities) for p in providers]}"
        )
    return min(eligible, key=lambda p: p.cost_per_second)


class SmartRouter:
    """Estrategia router. Genera una vez; si el gate falla, reintenta otra vez."""

    name = "router"

    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries

    async def run(
        self, scene: Scene, providers: list[BaseProvider], gate: QualityGate
    ) -> GenResult:
        provider = pick_provider(scene, providers)
        req = scene_to_request(scene)
        result = await provider.generate(req)
        report = await gate.evaluate(scene, result)
        attempts = 1
        while not report.passed and attempts <= self.max_retries:
            req.seed = (req.seed or 0) + 1  # variar para que el reintento difiera
            result = await provider.generate(req)
            report = await gate.evaluate(scene, result)
            attempts += 1
        result.raw_meta["gate_passed"] = report.passed
        result.raw_meta["gate_reason"] = report.reason
        result.raw_meta["attempts"] = attempts
        result.raw_meta["gate_scores"] = report_scores(report)
        return result
