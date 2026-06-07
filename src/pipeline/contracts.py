"""L0 - Contratos tipados que viajan entre capas.

Fijar estos tipos primero es la inversion que evita reescribir cuando entren
nuevas estrategias o proveedores. Todo lo demas depende de aqui.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SceneClass = Literal["hero", "standard", "volume"]

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
        """Traduce los flags a capabilities que el provider debe cumplir."""
        caps: set[str] = set()
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


class Shot(BaseModel):
    """Plano (D-028): unidad atomica keyframe+clip+audio dentro de una escena.

    El `framing` EXTIENDE el prompt de la escena (encuadre/accion); hereda
    setting/personajes/estilo. El plano 1 es el keyframe elegido por el humano;
    los planos 2+ se autogeneran en el render.
    """

    framing: str = ""  # encuadre/accion que se suma al prompt de la escena
    duration_s: float = Field(gt=0)
    seed: int = 0  # reroll del plano (cache miss solo en este plano)
    voiceover: Optional[str] = None  # audio del plano (TTS)
    caption: Optional[str] = None  # texto en pantalla del plano
    sfx: Optional[str] = None  # efectos de sonido de la accion (V2A MMAudio, D-034)
    keyframe: Optional[Path] = None  # rellenado por L3


class Scene(BaseModel):
    """Beat narrativo (D-028). Agrupa planos; comparte prompt base + personajes."""

    id: str
    prompt: str  # BASE (setting+personajes); el plano le suma su framing
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
    character_refs: list[Path] = Field(default_factory=list)  # transitorio: refs resueltas por el runner

    model_config = {"populate_by_name": True}


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
