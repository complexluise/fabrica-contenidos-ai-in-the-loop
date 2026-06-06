"""Settings centralizados (pydantic-settings v2).

Lee las API keys desde `.env` (gitignored) y desde variables de entorno reales,
con prioridad para estas ultimas. Un solo punto de verdad para credenciales.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # FAL_KEY -> fal_key
        extra="ignore",
    )

    # fal.ai: keyframe (Flux+LoRA) y video (Kling/Seedance...).
    fal_key: str | None = Field(default=None)
    # Anthropic: descomposicion de guion, clasificador y Quality Gate (VLM-judge).
    anthropic_api_key: str | None = Field(default=None)
    # Google: Veo (Sprint 2).
    google_api_key: str | None = Field(default=None)
    # ElevenLabs: voz en off por escena (TTS, Sprint 6).
    elevenlabs_api_key: str | None = Field(default=None)

    def require(self, attr: str, para: str) -> str:
        """Devuelve la key o lanza un error claro indicando para que se necesita."""
        value = getattr(self, attr)
        if not value:
            env_name = attr.upper()
            raise RuntimeError(
                f"Falta {env_name} ({para}). Ponla en .env o exportala como variable de entorno."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Singleton cacheado. Usar esto en vez de leer os.environ directamente."""
    return Settings()
