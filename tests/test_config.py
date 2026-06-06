"""Core: la config (YAML -> objetos tipados) alimenta routing y estilo. Critico."""

import pytest
from pathlib import Path

from pipeline.config import load_config, load_providers, load_routing

CONFIG_DIR = Path("config")


def test_load_config_real_files_typed():
    cfg = load_config(CONFIG_DIR, "lego")
    # providers con capabilities como set
    assert "kling" in cfg.providers
    assert cfg.providers["kling"].cost_per_second == 0.03
    assert "i2v" in cfg.providers["kling"].capabilities
    # routing con umbrales por clase
    assert set(cfg.routing.hybrid) == {"hero", "standard", "volume"}
    assert cfg.routing.hybrid["hero"].strategy == "ensemble"
    assert cfg.routing.thresholds["hero"]["aesthetic"] == 0.80
    # estilo
    assert cfg.style.style == "lego"
    assert "{scene_prompt}" in cfg.style.prompt_template


def test_providers_capabilities_are_sets():
    provs = load_providers(CONFIG_DIR / "providers.yaml")
    assert isinstance(provs["veo"].capabilities, set)
    assert "audio" in provs["veo"].capabilities


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_routing(Path("config") / "no_existe.yaml")
