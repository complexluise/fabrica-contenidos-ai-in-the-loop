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


def routing_gaps(spec, routing: RoutingConfig, providers: dict) -> list[dict]:
    """Escenas que NINGÚN provider del perfil puede generar (D-057).

    Para cada escena resuelve la regla efectiva (`select_rule`, respeta el fallback a
    'standard' de D-055) y verifica que al menos uno de SUS providers cumpla las
    capabilities exigidas (`required_capabilities()`, base `{i2v}` + flags, D-054).
    Devuelve `{scene, missing}` con las capabilities que nadie de la regla aporta.

    Lógica pura sobre config (no construye clientes): la consumen el aviso de firma
    (`state.signing_advisories`, no bloqueante) y el guard temprano del runner (falla
    antes de gastar). Una fuente de verdad, dos consumidores."""
    out: list[dict] = []
    for s in spec.scenes:
        required = s.requirements.required_capabilities()
        rule = select_rule(s.class_ or "standard", routing)
        names = [n for n in rule.providers if n in providers]
        # Elegible = UN solo provider cumple TODO lo exigido (igual que eligible_providers).
        if any(required <= providers[n].capabilities for n in names):
            continue
        available = set().union(*(providers[n].capabilities for n in names)) if names else set()
        out.append({"scene": s.id, "missing": sorted(required - available)})
    return out


def build_strategy(name: str):
    """Instancia la estrategia por nombre."""
    try:
        return _STRATEGIES[name]()
    except KeyError:
        raise ValueError(f"Estrategia desconocida: {name}. Usa {list(_STRATEGIES)}.")
