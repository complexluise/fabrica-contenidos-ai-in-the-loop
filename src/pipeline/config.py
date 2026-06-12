"""L0 - Carga y validacion de config (providers, routing, estilos).

Toda la parametrizacion vive en YAML para poder enrutar/cambiar estilo sin tocar
codigo. Aqui se valida y se convierte a objetos tipados.

Dos secciones independientes en routing.yaml (D-053):
  storyboard_backends  -> StoryboardConfig  (imagen + LLM narrativo)
  profiles             -> ProfileConfig      (video + gate)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# D-076: LA fuente del perfil por defecto. CLI y server la importan — gastar
# mas que ultra-cheap es siempre una decision explicita del humano.
DEFAULT_PROFILE = "fal-ultra-cheap"


class FinishConfig(BaseModel):
    """El "film stock" del estilo: ~8 escalares tuneables en el YAML (D-073)."""

    enabled: bool = True
    saturation: float = 0.9      # los colores de cine: saturados O luminosos, no ambos
    contrast: float = 1.02
    # Curva S con hombro fílmico: sombras levemente comprimidas, highlights con roll-off.
    curve: str = "0/0 0.25/0.22 0.5/0.5 0.75/0.78 1/0.97"
    vignette: bool = True
    halation_alpha: float = 0.12  # casi invisible: los coloristas avisan que se nota = mal
    halation_sigma: float = 30.0
    halation_threshold: int = 200  # solo highlights altos (Y > umbral)
    sharpen: float = 0.4
    grain: int = 7                # noise alls= (5-10 ~ 10-15% de opacidad 35mm)
    fps: int = 24                 # conformar TODO a una sola cadencia (mezclas = tell)
    lufs: float = -14.0           # Instagram/TikTok
    true_peak: float = -1.0


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
    # D-072: negative ESPECÍFICO de video (artefactos de movimiento: morphing,
    # slow motion, identity drift). El de imagen habla de pixeles; este, de tiempo.
    # Vacío -> cae al negative_prompt de imagen (compat).
    video_negative_prompt: str = ""
    # D-073: el "film stock" del estilo (grade+grano+mastering en ffmpeg, $0).
    finish: FinishConfig = Field(default_factory=FinishConfig)

    def effective_video_negative(self) -> str:
        """Negative para el modelo de VIDEO: el específico, o el de imagen (compat)."""
        return self.video_negative_prompt or self.negative_prompt


class StrategyRule(BaseModel):
    strategy: str  # "router" | "cascade" | "ensemble"
    providers: list[str]


class RoutingConfig(BaseModel):
    rules: dict[str, StrategyRule]  # perfil ya resuelto (D-038); era 'hybrid'
    thresholds: dict[str, dict[str, float]]
    enforce: bool = False  # gate suave por defecto (puntúa pero no bloquea)


# --- D-052/D-053: configuracion de roles AI ----------------------------------

class GateProfileConfig(BaseModel):
    """Control del gate por perfil de render: habilitado/deshabilitado + modelo VLM."""
    enabled: bool = True
    vlm_model: str | None = None  # None -> haiku; "gemini-*" -> Google VLM


class ProfileConfig(BaseModel):
    """Configuracion de la fase de PRODUCCION (render, run) — D-052.

    Solo habla de video: estrategia, gate y costo estimado por escena.
    El backend de imagen y el LLM narrativo viven en StoryboardConfig (D-053).
    """
    gate: GateProfileConfig = Field(default_factory=GateProfileConfig)
    est_cost_per_scene_usd: float = 0.05


class StoryboardKeyframeConfig(BaseModel):
    """Backend y modelos de imagen para el storyboard backend activo.

    `model`/`ref_model` PISAN a los del estilo cuando el preset los define
    (D-063: la palanca de calidad de imagen vive en el preset, no en el estilo;
    la config `model` de D-053 estaba muerta hasta este cableado)."""
    backend: str = "fal"
    model: str | None = None  # None -> usa el del estilo
    ref_model: str | None = None  # None -> usa el del estilo (edición/identidad)


class StoryboardLLMConfig(BaseModel):
    """LLM narrativo (naming, describe, classify, compile) para el backend activo."""
    backend: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"


class StoryboardConfig(BaseModel):
    """Configuracion de la fase CREATIVA (cast, keyframes, prompts) — D-053.

    Persiste en project.yaml como `storyboard_backend: fal`. Controla el backend
    de imagen y el LLM narrativo; independiente del perfil de render.
    """
    name: str = "fal"
    keyframe: StoryboardKeyframeConfig = Field(default_factory=StoryboardKeyframeConfig)
    llm: StoryboardLLMConfig = Field(default_factory=StoryboardLLMConfig)
    est_cost_per_image_usd: float = 0.003


class VoiceConfig(BaseModel):
    """Backend de TTS seleccionable (D-058) — eje independiente, patrón D-053.

    Persiste en project.yaml como `voice_backend: kokoro`. Default kokoro
    (fal-ai/kokoro, lo más barato para prototipar, D-052); elevenlabs para
    producción. Independiente del perfil de render: video barato + voz premium
    es una combinación válida.
    """
    name: str = "kokoro"
    backend: str = "kokoro"  # motor de TTS: "kokoro" (fal) | "elevenlabs"
    model: str = "fal-ai/kokoro"
    default_voice: str | None = "em_alex"  # voz si la escena/proyecto no fija voice_id
    cost_per_char: float = 0.0001


# --- Config raiz -------------------------------------------------------------

class Config(BaseModel):
    """Config raiz del pipeline."""

    providers: dict[str, ProviderConfig]
    routing: RoutingConfig
    style: StyleConfig
    # Post de audio (D-034): modelos que NO compiten en el routing.
    audio: dict[str, ProviderConfig] = Field(default_factory=dict)
    # Fase de produccion (D-052): gate + costo por escena.
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    # Fase creativa (D-053): backend de imagen + LLM narrativo.
    storyboard: StoryboardConfig = Field(default_factory=StoryboardConfig)
    # Voz (D-058): backend de TTS seleccionable (kokoro/elevenlabs), eje independiente.
    voice: VoiceConfig = Field(default_factory=VoiceConfig)


def narrative_model(storyboard: StoryboardConfig) -> str | None:
    """Modelo del LLM narrativo (compile/describe/classify) SI el backend es
    anthropic — el único implementado. Otro backend -> None y cada módulo usa su
    default Claude (la vía Gemini narrativa queda DIFERIDA, D-078). Antes
    `StoryboardLLMConfig` era config muerta: nadie la leía."""
    if storyboard.llm.backend == "anthropic":
        return storyboard.llm.model
    return None


# --- Loaders -----------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de config: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def providers_from(raw: dict) -> dict[str, ProviderConfig]:
    """Bloque `providers:` ya parseado -> configs tipadas. Pura (D-077)."""
    return {name: ProviderConfig(name=name, **spec)
            for name, spec in (raw.get("providers") or {}).items()}


def audio_from(raw: dict) -> dict[str, ProviderConfig]:
    """Bloque `audio:` ya parseado (post de audio, D-034). Pura (D-077)."""
    return {name: ProviderConfig(name=name, **spec)
            for name, spec in (raw.get("audio") or {}).items()}


def load_providers(path: Path) -> dict[str, ProviderConfig]:
    return providers_from(_load_yaml(path))


def load_audio(path: Path) -> dict[str, ProviderConfig]:
    """Modelos de post de audio (bloque `audio:` de providers.yaml). D-034."""
    return audio_from(_load_yaml(path))


# Claves de perfil de render que NO son reglas de routing (D-052/D-053).
_PROFILE_ROLE_KEYS = {"gate", "est_cost_per_scene_usd"}


def routing_from(raw: dict, profile: str = DEFAULT_PROFILE) -> RoutingConfig:
    """Routing del perfil solicitado desde el YAML ya parseado (D-038/D-052).

    Formato nuevo: `profiles.<profile>` en el YAML.
    Compat: si no hay `profiles:`, se asume bloque `hybrid:` como perfil prod.
    """
    raw = dict(raw)  # no mutar el dict compartido (se parsea UNA vez, D-077)
    if "profiles" in raw:
        profiles = raw.pop("profiles")
        raw.pop("storyboard_backends", None)  # no forma parte del routing
        chosen = profiles.get(profile) or profiles.get("fal-ultra-cheap") or profiles.get("prod") or {}
        rules = {k: v for k, v in chosen.items() if k not in _PROFILE_ROLE_KEYS and k != "_meta"}
    else:
        rules = raw.pop("hybrid", {})
    raw["rules"] = rules
    raw.pop("voice_backends", None)  # no forma parte del routing
    return RoutingConfig(**raw)


def load_routing(path: Path, profile: str = DEFAULT_PROFILE) -> RoutingConfig:
    return routing_from(_load_yaml(path), profile=profile)


def profile_from(raw: dict, profile: str = DEFAULT_PROFILE) -> ProfileConfig:
    """Configuracion de la fase de render del perfil activo (D-052). Pura.

    Perfiles sin secciones 'gate' usan los defaults de ProfileConfig (backward-compat).
    """
    profiles = raw.get("profiles", {})
    entry = profiles.get(profile) or profiles.get("fal-ultra-cheap") or {}

    gt_raw = entry.get("gate") or {}
    gt = GateProfileConfig(**gt_raw) if gt_raw else GateProfileConfig()

    return ProfileConfig(
        gate=gt,
        est_cost_per_scene_usd=entry.get("est_cost_per_scene_usd", 0.05),
    )


def load_profile_config(path: Path, profile: str = DEFAULT_PROFILE) -> ProfileConfig:
    return profile_from(_load_yaml(path), profile=profile)


def storyboard_from(raw: dict, backend: str = "fal") -> StoryboardConfig:
    """Configuracion del storyboard backend activo (D-053). Pura.

    Backends no encontrados caen a 'fal' (mas compatible).
    """
    backends = raw.get("storyboard_backends", {})
    entry = backends.get(backend) or backends.get("fal") or {}

    kf_raw = entry.get("keyframe") or {}
    lm_raw = entry.get("llm") or {}

    kf = StoryboardKeyframeConfig(**{k: v for k, v in kf_raw.items() if v is not None}) if kf_raw else StoryboardKeyframeConfig()
    lm = StoryboardLLMConfig(**{k: v for k, v in lm_raw.items() if v is not None}) if lm_raw else StoryboardLLMConfig()

    return StoryboardConfig(
        name=backend,
        keyframe=kf,
        llm=lm,
        est_cost_per_image_usd=entry.get("est_cost_per_image_usd", 0.003),
    )


def load_storyboard_config(path: Path, backend: str = "fal") -> StoryboardConfig:
    return storyboard_from(_load_yaml(path), backend=backend)


def voice_from(raw: dict, backend: str = "kokoro") -> VoiceConfig:
    """Backend de voz activo desde `voice_backends` (D-058). Pura.

    Backends no encontrados caen a 'kokoro' (el más barato; D-052)."""
    backends = raw.get("voice_backends", {})
    entry = backends.get(backend) or backends.get("kokoro") or {}
    name = backend if backend in backends else "kokoro"
    fields = {k: v for k, v in entry.items() if k != "_meta" and v is not None}
    return VoiceConfig(name=name, **fields)


def load_voice_config(path: Path, backend: str = "kokoro") -> VoiceConfig:
    return voice_from(_load_yaml(path), backend=backend)


def load_style(path: Path) -> StyleConfig:
    return StyleConfig(**_load_yaml(path))


def load_config(config_dir: Path, style: str, profile: str = DEFAULT_PROFILE,
                backend: str = "fal", voice_backend: str = "kokoro") -> Config:
    """Carga la config completa para un estilo, perfil de render, storyboard backend
    y backend de voz (D-052/D-053/D-058)."""
    # D-077: cada YAML se parsea UNA vez (antes routing.yaml se leia 4 veces).
    providers_raw = _load_yaml(config_dir / "providers.yaml")
    routing_raw = _load_yaml(config_dir / "routing.yaml")
    providers = providers_from(providers_raw)
    audio = audio_from(providers_raw)
    routing = routing_from(routing_raw, profile=profile)
    style_cfg = load_style(config_dir / "styles" / f"{style}.yaml")
    profile_cfg = profile_from(routing_raw, profile=profile)
    storyboard_cfg = storyboard_from(routing_raw, backend=backend)
    voice_cfg = voice_from(routing_raw, backend=voice_backend)
    # D-063: el preset de storyboard PISA los modelos de imagen del estilo (la
    # palanca de calidad). Sin preset explícito, el estilo manda (como siempre).
    if storyboard_cfg.keyframe.model:
        style_cfg.keyframe.model = storyboard_cfg.keyframe.model
    if storyboard_cfg.keyframe.ref_model:
        style_cfg.keyframe.ref_model = storyboard_cfg.keyframe.ref_model
    return Config(providers=providers, routing=routing, style=style_cfg, audio=audio,
                  profile=profile_cfg, storyboard=storyboard_cfg, voice=voice_cfg)
