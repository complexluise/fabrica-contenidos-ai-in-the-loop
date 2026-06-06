"""L5 - Dispatcher híbrido.

Mapea la clase de escena -> estrategia + subconjunto de providers, leyendo
`routing.yaml` (§4.4 del SPEC). Cambiar el YAML cambia el ruteo sin tocar código.
"""

from __future__ import annotations

from ..config import RoutingConfig, StrategyRule
from .cascade import Cascade
from .ensemble import Ensemble
from .router import SmartRouter

_STRATEGIES = {
    "router": SmartRouter,
    "cascade": Cascade,
    "ensemble": Ensemble,
}


def select_rule(scene_class: str, routing: RoutingConfig) -> StrategyRule:
    """Regla (estrategia + providers) para la clase de escena. Default: standard."""
    return routing.hybrid.get(scene_class) or routing.hybrid["standard"]


def build_strategy(name: str):
    """Instancia la estrategia por nombre."""
    try:
        return _STRATEGIES[name]()
    except KeyError:
        raise ValueError(f"Estrategia desconocida: {name}. Usa {list(_STRATEGIES)}.")
