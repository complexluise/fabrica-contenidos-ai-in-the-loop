"""Señal VLM-judge (multimodal): Claude o Gemini según el perfil activo (D-052).

Ahora SÍ mira un frame del clip (no solo el prompt): puntúa adherencia, estética,
consistencia y artefactos. El modelo se elige por perfil: si el vlm_model empieza
por "gemini" usa Google; si es un ID de Anthropic, usa la SDK de Anthropic.
Degrada con elegancia: sin key o vlm_model=None devuelve métricas vacías.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ..contracts import Scene
from ..settings import get_settings
from .fusion import parse_judge_metrics

_JUDGE_PROMPT = """Eres control de calidad de video IA. Mira el frame del clip y evalúalo contra
su prompt. Responde SOLO JSON: {{"aesthetic":0-1,"char_consistency":0-1,"clip_adherence":0-1,"artifacts":0-1,"reason":""}}
- aesthetic: calidad visual.
- char_consistency: consistencia de personajes/estilo.
- clip_adherence: cuánto respeta el prompt.
- artifacts: 0 limpio, 1 roto.
Prompt de la escena: {prompt}
"""

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # barato; el perfil prod usa Opus


def _image_block(frame: Path) -> dict:
    ext = Path(frame).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    data = base64.standard_b64encode(Path(frame).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


class VLMSignal:
    """Señal semántica multimodal. weight alto: es la más informada.

    vlm_model=None deshabilita la señal (perfil sin gate).
    Modelos "gemini-*" usan google-genai; los demás, anthropic SDK.
    """

    name = "vlm"
    weight = 2.0

    def __init__(self, vlm_model: str | None = _DEFAULT_MODEL):
        self._model = vlm_model  # None -> señal deshabilitada

    async def score(self, frame: Path, scene: Scene) -> dict:
        if not self._model:
            return {}
        if self._model.startswith("gemini"):
            return await self._score_google(frame, scene)
        return await self._score_anthropic(frame, scene)

    async def _score_anthropic(self, frame: Path, scene: Scene) -> dict:
        key = get_settings().anthropic_api_key
        if not key:
            return {}
        try:
            import anthropic
        except ImportError:  # pragma: no cover
            return {}

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=self._model,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    _image_block(frame),
                    {"type": "text", "text": _JUDGE_PROMPT.format(prompt=scene.prompt)},
                ],
            }],
        )
        metrics, _reason = parse_judge_metrics(msg.content[0].text)
        return metrics

    async def _score_google(self, frame: Path, scene: Scene) -> dict:
        """VLM-judge via Gemini. Requiere GOOGLE_API_KEY."""
        key = get_settings().google_api_key
        if not key:
            return {}
        try:
            from google import genai
            from google.genai import types
        except ImportError:  # pragma: no cover
            return {}

        import asyncio

        client = genai.Client(api_key=key)
        image_bytes = frame.read_bytes()
        ext = frame.suffix.lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

        prompt_text = _JUDGE_PROMPT.format(prompt=scene.prompt)
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            prompt_text,
        ]
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self._model,
                    contents=contents,
                ),
                timeout=30,
            )
            text = result.candidates[0].content.parts[0].text if result.candidates else ""
            metrics, _reason = parse_judge_metrics(text)
            return metrics
        except Exception:  # noqa: BLE001
            return {}
