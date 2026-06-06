"""L4 - Base de providers + factory.

La interfaz `Provider` (contracts.py) es lo unico que ve la orquestacion.
Cambiar de agregador (fal) a API directa es transparente aguas arriba.
"""

from __future__ import annotations

import time

from ..config import ProviderConfig
from ..contracts import GenRequest, GenResult


class BaseProvider:
    """Implementacion comun. Las subclases solo definen `_call`."""

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.name = cfg.name
        self.cost_per_second = cfg.cost_per_second
        self.capabilities = set(cfg.capabilities)

    def supports(self, required: set[str]) -> bool:
        """True si este provider cumple TODAS las capabilities exigidas."""
        return required.issubset(self.capabilities)

    def estimate_cost(self, duration_s: float) -> float:
        return round(self.cost_per_second * duration_s, 4)

    async def generate(self, req: GenRequest) -> GenResult:
        """Mide latencia y costo alrededor de la llamada concreta `_call`."""
        t0 = time.perf_counter()
        video_path, raw_meta = await self._call(req)
        latency = time.perf_counter() - t0
        return GenResult(
            video_path=video_path,
            provider=self.name,
            cost_usd=self.estimate_cost(req.duration_s),
            latency_s=round(latency, 3),
            raw_meta=raw_meta,
        )

    async def _call(self, req: GenRequest):  # pragma: no cover - I/O externo
        raise NotImplementedError


def build_provider(cfg: ProviderConfig) -> BaseProvider:
    """Factory: instancia el adapter correcto segun el backend."""
    if cfg.backend == "fal":
        from .fal_kling import FalProvider

        return FalProvider(cfg)
    if cfg.backend == "google":
        from .google_veo import GoogleVeoProvider

        return GoogleVeoProvider(cfg)
    raise ValueError(f"Backend desconocido: {cfg.backend}")
