"""Adapter ElevenLabs TTS: texto -> archivo de audio (mp3).

Una sola llamada HTTP (httpx, ya en el core) en vez de la SDK -> sin deps pesadas
([[prefer-apis-over-heavy-libs]]). Aislado y mockeable; se valida con smoke real,
no con unit tests (es I/O de red).

Doc: POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
"""

from __future__ import annotations

from pathlib import Path

import httpx

from ..audio import DEFAULT_VOICE_MODEL

_BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsTTS:
    """Sintetiza voz vía la API de ElevenLabs y escribe un mp3."""

    name = "elevenlabs"

    cost_per_char = 0.00024  # eleven_turbo_v2_5 pricing (USD/char)

    def __init__(self, api_key: str, model: str = DEFAULT_VOICE_MODEL, timeout: float = 120.0):
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def synthesize(self, text: str, voice_id: str, out_path: Path) -> Path:
        """Genera el audio de `text` con `voice_id` y lo guarda en `out_path` (mp3)."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{_BASE_URL}/{voice_id}"
        headers = {
            "xi-api-key": self._api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            _raise_clear(resp)
            out_path.write_bytes(resp.content)
        return out_path


def _raise_clear(resp: httpx.Response) -> None:
    """Traduce los errores HTTP típicos a un mensaje que nombra el problema."""
    if resp.is_success:
        return
    hints = {
        401: "ELEVENLABS_API_KEY inválida o ausente (revisa .env).",
        402: "La cuenta de ElevenLabs no tiene créditos/cuota (Payment Required).",
        404: "voice_id desconocido (revisa el voice_id del proyecto/escena).",
        422: "petición inválida (texto vacío o parámetros de voz no válidos).",
        429: "rate limit de ElevenLabs; reintenta más tarde.",
    }
    hint = hints.get(resp.status_code, f"HTTP {resp.status_code}.")
    raise RuntimeError(f"ElevenLabs TTS falló: {hint}")
