"""Señal VLM-judge (Claude visión, multimodal).

Ahora SÍ mira un frame del clip (no solo el prompt): puntúa adherencia, estética,
consistencia y artefactos. Degrada con elegancia: sin ANTHROPIC_API_KEY devuelve
métricas vacías (la señal se omite).
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


def _image_block(frame: Path) -> dict:
    ext = Path(frame).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    data = base64.standard_b64encode(Path(frame).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


class VLMSignal:
    """Señal semántica multimodal. weight alto: es la más informada."""

    name = "vlm"
    weight = 2.0

    async def score(self, frame: Path, scene: Scene) -> dict:
        key = get_settings().anthropic_api_key
        if not key:
            return {}  # sin key -> se omite
        try:
            import anthropic
        except ImportError:  # pragma: no cover
            return {}

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-opus-4-8",
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
