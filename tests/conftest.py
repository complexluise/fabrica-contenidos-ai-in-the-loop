"""Fixtures comunes y helpers para los tests del core."""

from __future__ import annotations

from pipeline.config import ProviderConfig
from pipeline.providers.base import BaseProvider


def make_provider(name: str, cost: float, caps: set[str]) -> BaseProvider:
    return BaseProvider(
        ProviderConfig(
            name=name, backend="fal", model=f"m/{name}",
            cost_per_second=cost, capabilities=caps,
        )
    )
