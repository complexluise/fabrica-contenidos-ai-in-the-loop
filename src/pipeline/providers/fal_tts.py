"""Adapter TTS via fal.ai (fal-ai/kokoro) — fallback cuando no hay ELEVENLABS_API_KEY.

Usa FAL_KEY (ya requerida para keyframes/video) -> sin coste adicional de suscripcion.
Kokoro soporta espanol con voces ef_dora (femenina) y em_alex (masculina).
Calidad suficiente para guias/borradores; para entrega final usar ElevenLabs.

Interfaz identica a ElevenLabsTTS.synthesize(text, voice_id, out_path).
`voice_id` aqui es el nombre de voz de Kokoro, no un ID de ElevenLabs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

# Voces Kokoro con soporte espanol (fal-ai/kokoro)
# voice_id en project.yaml debe ser uno de estos cuando se usa FalTTS.
SPANISH_VOICES = {
    "female": "ef_dora",   # voz femenina, espanol
    "male":   "em_alex",   # voz masculina, espanol
}
DEFAULT_VOICE = SPANISH_VOICES["female"]
FAL_MODEL = "fal-ai/kokoro"


class FalTTS:
    """Sintetiza voz via fal-ai/kokoro. Descarga el audio y lo guarda en out_path (mp3/wav)."""

    name = "fal_kokoro"

    cost_per_char = 0.0001  # fal-ai/kokoro pricing estimado (USD/char)

    def __init__(self, fal_key: str, model: str = FAL_MODEL):
        self._fal_key = fal_key
        self.model = model

    async def synthesize(self, text: str, voice_id: str, out_path: Path) -> Path:
        """Genera audio de `text` con `voice_id` (nombre de voz Kokoro) y lo guarda."""
        import fal_client

        out_path.parent.mkdir(parents=True, exist_ok=True)

        voice = voice_id or DEFAULT_VOICE
        client = fal_client.AsyncClient(key=self._fal_key)

        result = await client.subscribe(
            self.model,
            arguments={"prompt": text, "voice": voice, "speed": 0.95},
        )

        audio_url = _extract_url(result)
        await _download(audio_url, out_path)
        return out_path


def _extract_url(result) -> str:
    """Extrae la URL del audio del resultado de fal (dict o objeto)."""
    if isinstance(result, dict):
        af = result.get("audio_file") or result.get("audio") or {}
        if isinstance(af, dict):
            return af.get("url") or af.get("audio_url") or ""
        if isinstance(af, str):
            return af
        # fallback: busca cualquier campo que parezca URL
        for v in result.values():
            if isinstance(v, str) and v.startswith("http"):
                return v
    # objeto Pydantic / dataclass
    for attr in ("audio_file", "audio"):
        obj = getattr(result, attr, None)
        if obj:
            return getattr(obj, "url", None) or str(obj)
    raise RuntimeError(f"FalTTS: no se encontro URL de audio en resultado: {result!r}")


async def _download(url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
