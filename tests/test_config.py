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


def test_audio_block_loaded_from_config(tmp_path):
    # D-034: el modelo de post de audio vive en config (no hardcodeado), con su costo.
    cfg = load_config(CONFIG_DIR, "lego")
    assert "mmaudio" in cfg.audio
    assert cfg.audio["mmaudio"].model == "fal-ai/mmaudio-v2"
    assert cfg.audio["mmaudio"].cost_per_second == 0.001
    # y NO entra al routing (no compite con los providers de video)
    assert "mmaudio" not in cfg.providers


def test_audio_block_absent_is_empty(tmp_path):
    (tmp_path / "providers.yaml").write_text(
        "providers:\n  k:\n    backend: fal\n    model: m\n    cost_per_second: 0.0\n",
        encoding="utf-8",
    )
    from pipeline.config import load_audio

    assert load_audio(tmp_path / "providers.yaml") == {}


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_routing(Path("config") / "no_existe.yaml")
