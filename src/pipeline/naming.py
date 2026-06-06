"""Nombres semánticos legibles para artefactos (D-026).

El humano mira, elige y **toma los archivos a mano** (D-021/D-025), así que la
capa visible necesita un nombre legible — no el hash content-addressed, que
sigue siendo la **verdad del caché** (D-013). `_slugify`/`readable_name` son
lógica pura (core testeable); la derivación con Claude es I/O (smoke).
"""

from __future__ import annotations

import re
import unicodedata

from .settings import get_settings

_SLUG_MODEL = "claude-haiku-4-5-20251001"  # el modelo más barato (D-026)


def _slugify(text: str, max_words: int = 4) -> str:
    """Texto -> slug ascii corto (snake_case). Determinista, sin I/O."""
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", norm.lower())
    return "_".join(words[:max_words]) or "scene"


def readable_name(prefix: str, slug: str, idx: int, ext: str) -> str:
    """Nombre humano-facing: <prefix>_<slug>_<idx><ext>. Lógica pura."""
    return f"{prefix}_{slug}_{idx}{ext}"


def semantic_slug(text: str) -> str:
    """Slug descriptivo de un prompt. Claude (Haiku) si hay key; si no, `_slugify`."""
    return _slug_via_llm(text) or _slugify(text)


def _slug_via_llm(text: str) -> str | None:  # pragma: no cover - I/O externo
    """Pide a Claude (modelo más barato) 2-4 palabras clave; None si no hay key/falla."""
    key = get_settings().anthropic_api_key
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=_SLUG_MODEL,
            max_tokens=12,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Resume esta toma en 2-4 palabras clave para nombrar un archivo. "
                        "Solo minusculas ascii separadas por guion_bajo, sin tildes. "
                        f"Toma: {text}. Responde solo el slug."
                    ),
                }
            ],
        )
        return _slugify(msg.content[0].text)  # sanea aunque el modelo agregue ruido
    except Exception:
        return None
