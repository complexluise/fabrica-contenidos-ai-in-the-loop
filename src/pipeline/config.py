"""L0 - Carga y validacion de config (providers, routing, estilos).

Toda la parametrizacion vive en YAML para poder enrutar/cambiar estilo sin tocar
codigo. Aqui se valida y se convierte a objetos tipados.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    name: str
    backend: str  # "fal" | "google" | ...
    model: str
    cost_per_second: float = Field(ge=0)
    capabilities: set[str] = Field(default_factory=set)


class KeyframeConfig(BaseModel):
    backend: str
    model: str
    lora: str | None = None
    strength: float = 0.9
    ref_model: str | None = None  # modelo de edición con referencia (consistencia de personaje)
    cost_per_image: float = 0.003  # costo estimado por imagen generada (fal-ai/flux-lora)


class StyleConfig(BaseModel):
    style: str
    keyframe: KeyframeConfig
    prompt_template: str
    negative_prompt: str = ""


class StrategyRule(BaseModel):
    strategy: str  # "router" | "cascade" | "ensemble"
    providers: list[str]


class RoutingConfig(BaseModel):
    rules: dict[str, StrategyRule]  # perfil ya resuelto (D-038); era 'hybrid'
    thresholds: dict[str, dict[str, float]]
    enforce: bool = False  # gate suave por defecto (puntúa pero no bloquea)


class Config(BaseModel):
    """Config raiz del pipeline."""

    providers: dict[str, ProviderConfig]
    routing: RoutingConfig
    style: StyleConfig
    # Post de audio (D-034): modelos que NO compiten en el routing (p.ej. el paso
    # video-to-audio MMAudio). Viven aparte de `providers:` para no entrar al
    # router/cascade/ensemble. Vacio si no hay bloque `audio:`.
    audio: dict[str, ProviderConfig] = Field(default_factory=dict)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de config: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_providers(path: Path) -> dict[str, ProviderConfig]:
    raw = _load_yaml(path).get("providers", {})
    return {name: ProviderConfig(name=name, **spec) for name, spec in raw.items()}


def load_audio(path: Path) -> dict[str, ProviderConfig]:
    """Modelos de post de audio (bloque `audio:` de providers.yaml). D-034."""
    raw = _load_yaml(path).get("audio", {})
    return {name: ProviderConfig(name=name, **spec) for name, spec in raw.items()}


def load_routing(path: Path, profile: str = "prod") -> RoutingConfig:
    """Carga el routing resolviendo el perfil solicitado (D-038).

    Formato nuevo: `profiles.<profile>` en el YAML.
    Compat: si no hay `profiles:`, se asume bloque `hybrid:` como perfil prod.
    """
    raw = _load_yaml(path)
    if "profiles" in raw:
        profiles = raw.pop("profiles")
        rules = dict(profiles.get(profile) or profiles["prod"])
        rules.pop("_meta", None)  # metadata de display — no es una regla de routing
    else:
        rules = raw.pop("hybrid", {})
    raw["rules"] = rules
    return RoutingConfig(**raw)


def load_style(path: Path) -> StyleConfig:
    return StyleConfig(**_load_yaml(path))


def load_config(config_dir: Path, style: str, profile: str = "prod") -> Config:
    """Carga la config completa para un estilo y perfil dados (D-038)."""
    providers = load_providers(config_dir / "providers.yaml")
    audio = load_audio(config_dir / "providers.yaml")
    routing = load_routing(config_dir / "routing.yaml", profile=profile)
    style_cfg = load_style(config_dir / "styles" / f"{style}.yaml")
    return Config(providers=providers, routing=routing, style=style_cfg, audio=audio)
