"""L5 - Dispatcher híbrido.

Mapea la clase de escena -> estrategia + subconjunto de providers, leyendo
`routing.yaml` (§4.4 del SPEC). Cambiar el YAML cambia el ruteo sin tocar código.
"""

from __future__ import annotations

import logging

from ..config import RoutingConfig, StrategyRule
from .cascade import Cascade
from .ensemble import Ensemble
from .router import SmartRouter

logger = logging.getLogger(__name__)

_STRATEGIES = {
    "router": SmartRouter,
    "cascade": Cascade,
    "ensemble": Ensemble,
}


def select_rule(scene_class: str, routing: RoutingConfig) -> StrategyRule:
    """Regla (estrategia + providers) para la clase de escena. Default: standard.

    Si la clase no existe en el perfil de routing, cae a 'standard' pero lo AVISA
    (T7/D-055): antes esto era silencioso y el humano firmaba `class_: "epic"` sin
    enterarse de que se renderizaba como standard."""
    rule = routing.rules.get(scene_class)
    if rule is None:
        logger.warning(
            "Clase de escena '%s' no está en el perfil de routing (%s); se enruta como 'standard'.",
            scene_class, sorted(routing.rules),
        )
        return routing.rules["standard"]
    return rule


def build_strategy(name: str):
    """Instancia la estrategia por nombre."""
    try:
        return _STRATEGIES[name]()
    except KeyError:
        raise ValueError(f"Estrategia desconocida: {name}. Usa {list(_STRATEGIES)}.")
