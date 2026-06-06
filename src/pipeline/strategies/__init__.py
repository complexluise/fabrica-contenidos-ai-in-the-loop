"""L5 - Estrategias de orquestación + dispatcher híbrido."""

from .cascade import Cascade
from .dispatch import build_strategy, select_rule
from .ensemble import Ensemble
from .router import SmartRouter, pick_provider

__all__ = ["SmartRouter", "Cascade", "Ensemble", "pick_provider", "build_strategy", "select_rule"]
