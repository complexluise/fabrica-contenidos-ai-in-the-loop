"""Core: la config (YAML -> objetos tipados) alimenta routing y estilo. Critico."""

import pytest
from pathlib import Path

from pipeline.config import load_config, load_profile_config, load_providers, load_routing

CONFIG_DIR = Path("config")


def test_load_config_real_files_typed():
    # Perfil prod explícito para validar que las reglas del perfil premium cargan
    cfg = load_config(CONFIG_DIR, "lego", profile="prod")
    # providers con capabilities como set
    assert "kling" in cfg.providers
    assert cfg.providers["kling"].cost_per_second == 0.03
    assert "i2v" in cfg.providers["kling"].capabilities
    # routing con umbrales por clase
    assert set(cfg.routing.rules) == {"hero", "standard", "volume"}
    assert cfg.routing.rules["hero"].strategy == "ensemble"
    assert cfg.routing.thresholds["hero"]["aesthetic"] == 0.80
    # estilo
    assert cfg.style.style == "lego"
    assert "{scene_prompt}" in cfg.style.prompt_template


def test_providers_capabilities_are_sets():
    provs = load_providers(CONFIG_DIR / "providers.yaml")
    assert isinstance(provs["veo"].capabilities, set)
    # veo-2.0-generate-001 (D-043) es i2v; el audio nativo es de Veo 3, no de este modelo.
    assert "i2v" in provs["veo"].capabilities


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


# --- D-038: perfiles de calidad -----------------------------------------------

def test_profile_prod_mantiene_ensemble():
    routing = load_routing(CONFIG_DIR / "routing.yaml", profile="prod")
    assert routing.rules["hero"].strategy == "ensemble"
    assert set(routing.rules) == {"hero", "standard", "volume"}


def test_profile_proto_todo_router_kling():
    routing = load_routing(CONFIG_DIR / "routing.yaml", profile="proto")
    for clase in ("hero", "standard", "volume"):
        assert routing.rules[clase].strategy == "router"
        assert routing.rules[clase].providers == ["kling"]


def test_profile_desconocido_cae_a_ultra_cheap():
    # D-052: fallback al perfil mas barato, no al mas caro.
    routing = load_routing(CONFIG_DIR / "routing.yaml", profile="no_existe")
    assert routing.rules["hero"].strategy == "router"
    assert routing.rules["hero"].providers == ["kling"]


# --- D-052: perfiles multi-rol ------------------------------------------------

def test_profile_fal_ultra_cheap_es_default():
    cfg = load_config(CONFIG_DIR, "lego")  # sin profile= -> fal-ultra-cheap
    assert cfg.profile.gate.enabled is False
    assert cfg.profile.gate.vlm_model is None
    assert cfg.profile.est_cost_per_scene_usd == 0.01
    # D-053: storyboard config es independiente del perfil de render
    assert cfg.storyboard.keyframe.backend == "fal"
    assert cfg.storyboard.llm.backend == "anthropic"
    assert cfg.storyboard.llm.model == "claude-haiku-4-5-20251001"


def test_profile_prod_gate_habilitado():
    cfg = load_config(CONFIG_DIR, "lego", profile="prod")
    assert cfg.profile.gate.enabled is True
    assert cfg.profile.gate.vlm_model == "claude-opus-4-8"
    assert cfg.profile.est_cost_per_scene_usd == 0.15


def test_profile_gemini_budget_google_first():
    # gemini-budget activa Veo + gate Gemini; storyboard backend es independiente
    cfg = load_config(CONFIG_DIR, "lego", profile="gemini-budget")
    assert cfg.profile.gate.enabled is True
    assert cfg.profile.gate.vlm_model == "gemini-2.0-flash"
    assert cfg.profile.est_cost_per_scene_usd == 0.02
    # Para storyboard 100% Google hay que pasar backend="google" explicitamente
    assert cfg.storyboard.keyframe.backend == "fal"  # default sin --backend google


def test_profile_routing_no_contiene_claves_de_rol():
    # Las secciones 'keyframe'/'gate'/'llm' no deben aparecer como reglas de routing.
    routing = load_routing(CONFIG_DIR / "routing.yaml", profile="fal-ultra-cheap")
    assert "keyframe" not in routing.rules
    assert "gate" not in routing.rules
    assert "llm" not in routing.rules
    assert set(routing.rules) == {"hero", "standard", "volume"}


def test_profile_config_backward_compat(tmp_path):
    # Perfil sin secciones de rol -> ProfileConfig con defaults (no rompe).
    (tmp_path / "routing.yaml").write_text(
        "profiles:\n"
        "  simple:\n"
        "    hero:\n"
        "      strategy: router\n"
        "      providers: [kling]\n"
        "    standard:\n"
        "      strategy: router\n"
        "      providers: [kling]\n"
        "    volume:\n"
        "      strategy: router\n"
        "      providers: [kling]\n"
        "enforce: false\n"
        "thresholds:\n"
        "  hero: {aesthetic: 0.8, char_consistency: 0.85, clip_adherence: 0.75}\n"
        "  standard: {aesthetic: 0.65, char_consistency: 0.7, clip_adherence: 0.65}\n"
        "  volume: {aesthetic: 0.5, char_consistency: 0.55, clip_adherence: 0.55}\n",
        encoding="utf-8",
    )
    profile_cfg = load_profile_config(tmp_path / "routing.yaml", profile="simple")
    assert profile_cfg.gate.enabled is True   # default conservador
    assert profile_cfg.est_cost_per_scene_usd == 0.05  # default


def test_fal_standard_gate_con_haiku():
    cfg = load_config(CONFIG_DIR, "lego", profile="fal-standard")
    assert cfg.profile.gate.enabled is True
    assert cfg.profile.gate.vlm_model == "claude-haiku-4-5-20251001"
    assert cfg.profile.est_cost_per_scene_usd == 0.05


# --- D-078: el LLM narrativo del perfil se cablea de verdad --------------------

def test_narrative_model_only_for_anthropic_backend():
    from pipeline.config import StoryboardConfig, StoryboardLLMConfig, narrative_model

    sb = StoryboardConfig(llm=StoryboardLLMConfig(backend="anthropic", model="claude-x"))
    assert narrative_model(sb) == "claude-x"
    sb_g = StoryboardConfig(llm=StoryboardLLMConfig(backend="google", model="gemini-2.0-flash"))
    assert narrative_model(sb_g) is None  # narrativa via Gemini: diferida (D-078)
