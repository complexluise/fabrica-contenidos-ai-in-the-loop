"""L5 - Parallel Ensemble / Best-of-N.

Genera N candidatos en paralelo (asyncio) entre los providers elegibles, los
puntúa con el gate y elige el mejor. Máxima calidad, máximo costo: se paga N
generaciones. Reservado a escenas hero (lo decide el dispatcher híbrido).
"""

from __future__ import annotations

import asyncio

from ..contracts import GenResult, QualityGate, ShotJob
from ..gate import gate_score, report_scores
from .common import eligible_providers, job_to_request


class Ensemble:
    name = "ensemble"

    async def run(self, job: ShotJob, providers: list, gate: QualityGate) -> GenResult:
        elig = eligible_providers(job, providers)
        if not elig:
            raise ValueError(f"Ensemble: ningún provider cumple los requisitos de {job.id}.")

        req = job_to_request(job)
        # Tolerante: un provider que falla (p.ej. Veo sin key) no tumba la escena.
        gen = await asyncio.gather(*(p.generate(req) for p in elig), return_exceptions=True)
        results = [r for r in gen if not isinstance(r, BaseException)]
        if not results:
            raise RuntimeError(f"Ensemble: todos los providers fallaron para {job.id}.")
        reports = await asyncio.gather(*(gate.evaluate(job, r) for r in results))

        total_cost = round(sum(r.cost_usd for r in results), 4)
        wall_latency = round(max(r.latency_s for r in results), 3)  # corren en paralelo

        scored = [
            (res, rep, gate_score(rep)) for res, rep in zip(results, reports)
        ]
        # Prefiere los que pasan el gate; si ninguno pasa, elige el mejor score igual.
        passing = [t for t in scored if t[1].passed]
        pool = passing if passing else scored
        best_res, best_rep, best_score = max(pool, key=lambda t: t[2])

        best_res.cost_usd = total_cost  # se pagó por todos
        best_res.latency_s = wall_latency
        best_res.raw_meta.update(
            {
                "gate_passed": best_rep.passed,
                "candidates": [(r.provider, round(s, 3)) for r, _, s in scored],
                "selected_score": round(best_score, 3),
                "gate_scores": report_scores(best_rep),
                # D-068: las tomas perdedoras están PAGADAS — se conservan como
                # cobertura para la edición, no se tiran.
                "alternate_takes": [
                    {"provider": r.provider, "video_path": str(r.video_path),
                     "score": round(sc, 3)}
                    for r, _, sc in scored if r is not best_res
                ],
            }
        )
        return best_res
