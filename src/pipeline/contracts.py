"""L0 - Contratos tipados que viajan entre capas.

Fijar estos tipos primero es la inversion que evita reescribir cuando entren
nuevas estrategias o proveedores. Todo lo demas depende de aqui.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SceneClass = Literal["hero", "standard", "volume"]

# --- Gramatica audiovisual del plano (D-047) -------------------------------
# Vocabulario controlado del shot-list (StudioBinder; herencia de las 5 C's de
# Mascelli) + estructura visual (Bruce Block, "The Visual Story"). Es lo que un
# DP/realizador piensa: el artefacto storyboard se vuelve componible y enseña la
# gramatica, y `prompt_compile` lo ensambla en el prompt de generacion.

# Tamanos de plano: extreme close-up ... extreme long shot (+ insert/detalle).
ShotSize = Literal["ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS", "insert"]
# Angulo de camara (ots = over-the-shoulder; worm = contrapicado extremo).
CameraAngle = Literal["eye", "high", "low", "overhead", "worm", "dutch", "ots"]
# Movimiento de camara.
CameraMove = Literal[
    "static", "pan", "tilt", "push_in", "pull_out", "track", "crane", "handheld", "zoom",
]
# Profundidad de campo / foco (rack = foco que viaja entre planos).
FocusDepth = Literal["deep", "shallow", "rack"]
# Tono/valor de iluminacion (Block): clave alta, clave baja, neutro, silueta.
ToneKey = Literal["high_key", "low_key", "neutral", "silhouette"]
# Transicion hacia el plano siguiente.
Transition = Literal["cut", "match_cut", "dissolve", "smash_cut", "wipe"]

# Capabilities que una escena puede exigir y un provider puede ofrecer.
Capability = Literal["i2v", "audio", "lipsync", "4k", "camera", "hdr", "multishot"]


class SceneRequirements(BaseModel):
    """Requisitos tecnicos de una escena. Determinan a que modelos puede ir."""

    needs_audio: bool = False  # dialogo sincronizado -> dispara Veo
    needs_lipsync: bool = False
    needs_4k: bool = False
    needs_camera_control: bool = False
    needs_hdr: bool = False

    def required_capabilities(self) -> set[str]:
        """Traduce los flags a capabilities que el provider debe cumplir.

        `i2v` es la base que SIEMPRE se exige: todo el pipeline genera video a
        partir de un keyframe (image-to-video). Declararlo evita que un provider
        text-to-video puro entre al routing sin que nadie lo descarte (D-054).
        """
        caps: set[str] = {"i2v"}
        if self.needs_audio:
            caps.add("audio")
        if self.needs_lipsync:
            caps.add("lipsync")
        if self.needs_4k:
            caps.add("4k")
        if self.needs_camera_control:
            caps.add("camera")
        if self.needs_hdr:
            caps.add("hdr")
        return caps


class Camera(BaseModel):
    """Gramatica de camara del plano (D-047): tamano, angulo, movimiento, foco.

    Vocabulario controlado (shot-list / 5 C's). `prompt_compile.compose_shot_visual`
    lo traduce a lenguaje natural para el prompt de generacion.
    """

    size: ShotSize = "MS"
    angle: CameraAngle = "eye"
    move: CameraMove = "static"
    focus: FocusDepth = "deep"
    lens_mm: Optional[int] = None  # opcional: precision de lente para quien la quiera

    def is_default(self) -> bool:
        """True si es la camara por defecto (para no ensuciar el YAML ni el prompt)."""
        return (self.size == "MS" and self.angle == "eye" and self.move == "static"
                and self.focus == "deep" and self.lens_mm is None)


class Visual(BaseModel):
    """Estructura visual del plano (D-047, Bruce Block "The Visual Story").

    Los componentes que cargan mood y construyen contraste ENTRE cortes:
    tono/valor, color, profundidad (fg/mg/bg), punto focal, linea, ritmo, y los
    graficos en pantalla (lower-third / tipografia cinetica / sellos).
    """

    tone: Optional[ToneKey] = None
    palette: list[str] = Field(default_factory=list)  # colores dominantes
    foreground: Optional[str] = None
    midground: Optional[str] = None
    background: Optional[str] = None
    focal_point: Optional[str] = None  # donde va el ojo del espectador
    line: Optional[str] = None  # lineas/direccion dominante de la composicion
    rhythm: Optional[str] = None  # ritmo visual (estatico, dinamico, repetitivo)
    graphics: Optional[str] = None  # texto en pantalla / lower-third / tipografia

    def is_empty(self) -> bool:
        """True si no se lleno ninguna dimension (para omitir del YAML/prompt)."""
        return not any([
            self.tone, self.palette, self.foreground, self.midground, self.background,
            self.focal_point, self.line, self.rhythm, self.graphics,
        ])


class Shot(BaseModel):
    """Plano (D-028) elevado a artefacto audiovisual (D-047).

    Un plano se define en cuatro ejes: **intencion** (funcion dramatica),
    **camera** (gramatica), **visual** (estructura de Block) y **sonido**
    (vo/caption/sfx), mas la **transicion** al siguiente. El `action` es el
    visual primario ("que se ve"); `framing` queda como LEGACY/fallback. El
    plano 1 es el keyframe elegido por el humano; los planos 2+ se autogeneran.
    """

    # --- narrativa / intencion ---
    intention: Optional[str] = None  # funcion dramatica: que comunica este plano (D-047)
    action: Optional[str] = None  # que SE VE / que pasa; visual primario (D-047)
    duration_s: float = Field(gt=0)
    seed: int = 0  # reroll del plano (cache miss solo en este plano)
    # --- gramatica + estructura visual (D-047) ---
    camera: Camera = Field(default_factory=Camera)
    visual: Visual = Field(default_factory=Visual)
    transition: Optional[Transition] = None  # como entra al plano siguiente
    # --- sonido ---
    voiceover: Optional[str] = None  # audio del plano (TTS)
    caption: Optional[str] = None  # texto en pantalla del plano
    sfx: Optional[str] = None  # efectos de sonido de la accion (V2A MMAudio, D-034)
    # --- legacy / generacion ---
    framing: str = ""  # LEGACY (D-028): fallback si `action` vacio; aun extiende el prompt
    keyframe: Optional[Path] = None  # rellenado por L3


class Scene(BaseModel):
    """Beat narrativo (D-028). Agrupa planos; comparte prompt base + personajes."""

    id: str
    prompt: str  # BASE (setting+personajes); el plano le suma su framing
    prompt_manual: bool = False  # D-046: el humano sobrescribio el prompt a mano (no recompilar solo)
    prompt_src_hash: Optional[str] = None  # D-046: narrative_hash() al compilar el prompt
    duration_s: float = Field(gt=0)
    beat: Optional[str] = None  # etiqueta narrativa del beat (para el guion de export, D-029)
    characters: list[str] = Field(default_factory=list)  # consistencia entre tomas
    dialogue: Optional[str] = None
    class_: Optional[SceneClass] = Field(default=None, alias="class")
    requirements: SceneRequirements = Field(default_factory=SceneRequirements)
    shots: list[Shot] = Field(default_factory=list)  # planos (D-028); vacio = 1 plano implicito
    keyframe: Optional[Path] = None  # rellenado por L3 (plano 1 = keyframe elegido)
    seed: int = 0  # knob de reroll: subirlo regenera SOLO esta escena (cache miss)
    caption: Optional[str] = None  # texto en pantalla (lower-third), opcional
    voiceover: Optional[str] = None  # texto narrado (TTS ElevenLabs), opcional
    voice_id: Optional[str] = None  # override de voz por escena (si no, default del proyecto)
    ambience: Optional[str] = None  # sonido del lugar (V2A MMAudio, por escena, D-034)
    visual_intensity: Optional[int] = None  # 1-5: curva de intensidad visual del video (D-047, Block)
    character_refs: list[Path] = Field(default_factory=list)  # transitorio: refs resueltas por el runner

    model_config = {"populate_by_name": True}

    def narrative_hash(self) -> str:
        """Hash de la narrativa que alimenta el prompt visual (D-046).

        Define cuando el prompt quedo 'desactualizado': si la narrativa cambio
        desde la ultima compilacion, este hash difiere de `prompt_src_hash`. Solo
        campos de la escena (beat/ambience/dialogue/personajes); el `design` de
        cada personaje vive en el banco y no se rastrea aca (limitacion asumida).
        """
        parts = [
            (self.beat or "").strip(),
            (self.ambience or "").strip(),
            (self.dialogue or "").strip(),
            "|".join(self.characters),
        ]
        payload = "\x01".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]

    @property
    def prompt_stale(self) -> bool:
        """True si el prompt es auto y la narrativa cambio desde la ultima compilacion.

        Los prompts `manual` nunca se reportan stale (el humano los firmo a mano);
        muestran su propio estado. Sin `prompt_src_hash` (nunca compilado) -> stale.
        """
        return not self.prompt_manual and self.prompt_src_hash != self.narrative_hash()


class GenRequest(BaseModel):
    """Lo que ve CUALQUIER provider. Desacopla la escena del backend concreto."""

    prompt: str
    duration_s: float = Field(gt=0)
    aspect_ratio: str = "9:16"
    init_image: Optional[Path] = None  # keyframe de estilo (image-to-video)
    ref_images: list[Path] = Field(default_factory=list)
    seed: Optional[int] = None


class GenResult(BaseModel):
    """Lo que devuelve CUALQUIER provider. Incluye telemetria desde el dia 1."""

    video_path: Path
    provider: str
    cost_usd: float = Field(ge=0)
    latency_s: float = Field(ge=0)
    raw_meta: dict = Field(default_factory=dict)


class GateReport(BaseModel):
    """Veredicto del Quality Gate sobre un GenResult."""

    passed: bool
    aesthetic: float = 0.0
    char_consistency: float = 0.0
    clip_adherence: float = 0.0
    artifacts: float = 0.0  # 0 = limpio, 1 = roto
    reason: str = ""


# --- Interfaces (Protocols) -------------------------------------------------


@runtime_checkable
class Provider(Protocol):
    """Un backend de generacion de video. Router/Cascade/Ensemble operan sobre listas de estos."""

    name: str
    cost_per_second: float
    capabilities: set[str]

    async def generate(self, req: GenRequest) -> GenResult: ...


@runtime_checkable
class QualityGate(Protocol):
    async def evaluate(self, scene: Scene, result: GenResult) -> GateReport: ...


@runtime_checkable
class Strategy(Protocol):
    async def run(
        self, scene: Scene, providers: list[Provider], gate: QualityGate
    ) -> GenResult: ...
