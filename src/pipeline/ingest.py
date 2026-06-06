"""L1 - Ingesta y descomposicion del guion en escenas.

Dos caminos:
  - Brief YAML con escenas ya listadas (deterministico, ideal para MVP/smoke).
  - Guion en prosa -> Claude lo descompone en `list[Scene]` (JSON estructurado).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .contracts import Scene
from .settings import get_settings

_DECOMP_PROMPT = """Eres un asistente de produccion de video. Descompon el guion en escenas.
Devuelve SOLO un array JSON. Cada escena: {{"id","prompt","duration_s","characters","dialogue"}}.
- prompt: descripcion visual de la toma (sin dialogo).
- duration_s: numero en segundos (entre 2 y 8).
- characters: lista de nombres que aparecen.
- dialogue: texto hablado o null.

Guion:
{script}
"""


_TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".text"}


def extract_text(path: Path) -> str:
    """Lee texto plano de un `.md`/`.txt` (entrada de la app, D-033).

    Sólo formatos de texto por ahora; `.docx`/`.pdf` quedan diferidos a una fase
    siguiente (ver `app/ROADMAP.md`). La descomposición la hace `author.draft_project`.
    """
    path = Path(path)
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        raise ValueError(
            f"Formato no soportado: '{path.suffix}'. Usa .md o .txt (pegá el texto si es otro)."
        )
    return path.read_text(encoding="utf-8")


def load_brief(path: Path) -> list[Scene]:
    """Carga escenas desde un brief YAML. Si trae 'script', delega a Claude."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "scenes" in data:
        return [Scene(**s) for s in data["scenes"]]
    if "script" in data:
        return decompose_script(data["script"])
    raise ValueError("El brief debe tener 'scenes' o 'script'.")


def decompose_script(script: str) -> list[Scene]:
    """Usa Claude para convertir prosa en escenas estructuradas."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Instala el extra [apis] para usar Claude: pip install -e .[apis]") from exc

    key = get_settings().require("anthropic_api_key", "descomposicion de guion")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        messages=[{"role": "user", "content": _DECOMP_PROMPT.format(script=script)}],
    )
    text = msg.content[0].text
    return parse_scenes(text)


def parse_scenes(text: str) -> list[Scene]:
    """Extrae el array JSON de la respuesta del LLM y lo valida. Testeable."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No se encontro array JSON en la respuesta: {text[:200]}")
    raw = json.loads(text[start : end + 1])
    return [Scene(**s) for s in raw]
