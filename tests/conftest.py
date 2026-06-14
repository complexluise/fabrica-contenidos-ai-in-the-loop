"""Fixtures comunes y helpers para los tests del core."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.config import ProviderConfig
from pipeline.providers.base import BaseProvider


def make_provider(name: str, cost: float, caps: set[str]) -> BaseProvider:
    return BaseProvider(
        ProviderConfig(
            name=name, backend="fal", model=f"m/{name}",
            cost_per_second=cost, capabilities=caps,
        )
    )


# ---------------------------------------------------------------------------
# Aislamiento de telemetria/jobs: ningun test debe tocar out/telemetry.sqlite
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirige LEDGER_PATH a un SQLite temporal para TODA la suite.

    Tanto JobManager como Telemetry / costs_summary resuelven db_path en
    tiempo de LLAMADA (no de definicion de la firma), de modo que parchear
    la constante con monkeypatch es suficiente para aislar CUALQUIER uso
    sin db_path explicito — incluyendo las rutas de produccion del server.

    Cubre los dos modulos que importan LEDGER_PATH:
      - pipeline.server.jobs  (JobManager.__init__)
      - pipeline.telemetry    (Telemetry.__init__, costs_summary)
    """
    fake_ledger = tmp_path / "test_telemetry.sqlite"
    monkeypatch.setattr("pipeline.server.jobs.LEDGER_PATH", fake_ledger)
    monkeypatch.setattr("pipeline.telemetry.LEDGER_PATH", fake_ledger)
