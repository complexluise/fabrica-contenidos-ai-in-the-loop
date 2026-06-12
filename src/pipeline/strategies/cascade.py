"""L5 - Cascade Fallback.

Intenta SIEMPRE primero el tier más barato (orden de la lista). Si el gate
falla, escala al siguiente. Se paga cada intento. Si ninguno pasa, marca para
cola humana. El costo final = suma de todos los tiers intentados.
"""

from __future__ import annotations

from ..contracts import GenResult, QualityGate, ShotJob
from ..gate import report_scores
from .common import eligible_providers, job_to_request


class Cascade:
    name = "cascade"

    async def run(self, job: ShotJob, providers: list, gate: QualityGate) -> GenResult:
        elig = eligible_providers(job, providers)
        if not elig:
            raise ValueError(f"Cascade: ningún provider cumple los requisitos de {job.id}.")

        req = job_to_request(job)
        total_cost = 0.0
        total_latency = 0.0
        tried: list[str] = []
        last: GenResult | None = None

        for provider in elig:  # orden = tiers (barato -> caro)
            result = await provider.generate(req)
            total_cost += result.cost_usd
            total_latency += result.latency_s
            tried.append(provider.name)
            last = result
            report = await gate.evaluate(job, result)
            if report.passed:
                result.cost_usd = round(total_cost, 4)
                result.latency_s = round(total_latency, 3)
                result.raw_meta.update({
                    "gate_passed": True, "tiers_tried": tried,
                    "gate_reason": report.reason, "gate_scores": report_scores(report),
                })
                return result

        # Ningún tier pasó -> cola humana.
        last.cost_usd = round(total_cost, 4)
        last.latency_s = round(total_latency, 3)
        last.raw_meta.update({
            "gate_passed": False, "tiers_tried": tried, "needs_human": True,
            "gate_reason": report.reason,  # D-076: el porqué también al fallar
            "gate_scores": report_scores(report),
        })
        return last
