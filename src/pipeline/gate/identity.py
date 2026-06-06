"""Señal de consistencia de personaje (API-first, sin insightface).

Claude visión compara el frame del clip contra la(s) imagen(es) de referencia del
personaje y puntúa la consistencia de identidad. Solo aporta `char_consistency` y
solo cuando la escena trae referencias (las pobla el runner) y hay key.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..contracts import Scene
from ..settings import get_settings
from .vlm import _image_block

_PROMPT = """Compara la identidad del personaje. La(s) primera(s) imagen(es) son la REFERENCIA del
personaje; la última es un FRAME de un clip generado. Responde SOLO JSON:
{"char_consistency":0-1,"reason":""}
- char_consistency: 1 = mismo personaje (rasgos/atuendo/color), 0 = distinto.
"""


class IdentitySignal:
    name = "identity"
    weight = 2.0  # señal fuerte y específica de consistencia

    async def score(self, frame: Path, scene: Scene) -> dict:
        refs = getattr(scene, "character_refs", []) or []
        if not refs:
            return {}
        key = get_settings().anthropic_api_key
        if not key:
            return {}
        try:
            import anthropic
        except ImportError:  # pragma: no cover
            return {}

        content = [_image_block(r) for r in refs[:3]]  # hasta 3 referencias
        content.append(_image_block(frame))
        content.append({"type": "text", "text": _PROMPT})

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            messages=[{"role": "user", "content": content}],
        )
        text = msg.content[0].text
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return {}
        data = json.loads(text[start : end + 1])
        return {"char_consistency": float(data.get("char_consistency", 0.0))}
