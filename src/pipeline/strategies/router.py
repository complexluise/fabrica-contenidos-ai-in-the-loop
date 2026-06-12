"""L5 - Smart Cost Router.

En un solo paso, despacha el plano al provider MAS BARATO que cumple sus
requisitos. La logica de seleccion (`pick_provider`) es pura -> es core testeable
porque decide el costo de toda la produccion.
"""

from __future__ import annotations

from ..contracts import GenResult, QualityGate, ShotJob
from ..gate import report_scores
from ..providers.base import BaseProvider
from .common import eligible_providers, job_to_request


def pick_provider(job: ShotJob, providers: list[BaseProvider]) -> BaseProvider:
    """El mas barato que cumple las capabilities exigidas por el plano.

    Lanza si ningun provider cumple (mejor fallar fuerte que mandar a uno incapaz).
    """
    eligible = eligible_providers(job, providers)
    if not eligible:
        required = job.requirements.required_capabilities()
        raise ValueError(
            f"Ningun provider cumple {required or '{}'} para el plano {job.id}. "
            f"Disponibles: {[(p.name, p.capabilities) for p in providers]}"
        )
    return min(eligible, key=lambda p: p.cost_per_second)


class SmartRouter:
    """Estrategia router. Genera una vez; si el gate falla, reintenta otra vez."""

    name = "router"

    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries

    async def run(
        self, job: ShotJob, providers: list[BaseProvider], gate: QualityGate
    ) -> GenResult:
        provider = pick_provider(job, providers)
        req = job_to_request(job)
        result = await provider.generate(req)
        report = await gate.evaluate(job, result)
        attempts = 1
        # D-076: el costo/latencia del plano = TODOS los intentos (el reintento
        # fallido también se pagó; Cascade y Ensemble ya acumulaban — el router no).
        total_cost = result.cost_usd
        total_latency = result.latency_s
        while not report.passed and attempts <= self.max_retries:
            req.seed = (req.seed or 0) + 1  # variar para que el reintento difiera
            result = await provider.generate(req)
            total_cost += result.cost_usd
            total_latency += result.latency_s
            report = await gate.evaluate(job, result)
            attempts += 1
        result.cost_usd = round(total_cost, 4)
        result.latency_s = round(total_latency, 3)
        result.raw_meta["gate_passed"] = report.passed
        result.raw_meta["gate_reason"] = report.reason
        result.raw_meta["attempts"] = attempts
        result.raw_meta["gate_scores"] = report_scores(report)
        return result
