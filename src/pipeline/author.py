"""L1 - Autoría asistida: texto libre -> borrador de proyecto (D-033, Fase 2 app).

El Checkpoint #1 de [D-021] hecho interfaz: la persona pega/sube un texto y la IA
**propone** un borrador (título, brief, escenas con planos); luego la persona lo
**edita y firma** en el storyboard. La IA descompone; la persona decide.

`parse_draft` es lógica pura (testeable: parseo del JSON del LLM); `draft_project`
es I/O (Claude, smoke). El borrador se materializa con `project.write_spec`.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .contracts import Scene
from .settings import get_settings

_DRAFT_MODEL = "claude-opus-4-8"

_DRAFT_PROMPT = """Eres un asistente de producción de video. Convierte el texto en un
BORRADOR de proyecto que un humano luego editará. Devuelve SOLO un objeto JSON:

{{
  "title": "título corto y claro",
  "brief": "sinopsis de 1-2 frases",
  "scenes": [
    {{
      "id": "s1",
      "prompt": "descripción visual del beat (setting + personajes, SIN diálogo)",
      "duration_s": 5,
      "beat": "etiqueta narrativa corta (p.ej. 'apertura')",
      "characters": ["nombres que aparecen"],
      "shots": [
        {{"framing": "encuadre/acción del plano", "duration_s": 3,
          "voiceover": "texto narrado o null", "caption": "texto en pantalla o null"}}
      ]
    }}
  ]
}}

Reglas:
- prompt: lo VISUAL del beat; el plano (framing) le suma el encuadre.
- duration_s: número en segundos (2 a 8). El de la escena = suma de sus planos.
- Si una escena tiene un solo plano, igual incluí "shots" con ese plano.
- No inventes personajes si el texto no los nombra.

Texto:
{text}
"""


class ProjectDraft(BaseModel):
    """Borrador editable de un proyecto, propuesto por la IA desde texto libre."""

    title: str = "Proyecto sin título"
    brief: str = ""
    style: str = "lego"
    format: str = "9:16"
    scenes: list[Scene] = Field(default_factory=list)

    def to_spec(self, slug: str):
        """Convierte el borrador en un ProjectSpec listo para `write_spec`."""
        from .project import ProjectSpec

        return ProjectSpec(
            slug=slug,
            style=self.style,
            format=self.format,
            scenes=self.scenes,
            title=self.title,
            brief=self.brief,
        )


def _scene_from_raw(raw: dict, idx: int) -> Scene:
    """Normaliza una escena del LLM en un Scene válido (rellena lo que falte)."""
    s = dict(raw)
    s.setdefault("id", f"s{idx + 1}")
    # duration_s es obligatorio (>0): derivar de los planos o caer a un default.
    if not s.get("duration_s"):
        shots = s.get("shots") or []
        total = sum(float(sh.get("duration_s") or 0) for sh in shots)
        s["duration_s"] = total or 5
    return Scene(**s)


def parse_draft(text: str) -> ProjectDraft:
    """Extrae el objeto JSON de la respuesta del LLM y lo valida. Lógica pura."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No se encontró objeto JSON en la respuesta: {text[:200]}")
    raw = json.loads(text[start : end + 1])
    scenes = [_scene_from_raw(s, i) for i, s in enumerate(raw.get("scenes") or [])]
    return ProjectDraft(
        title=raw.get("title") or "Proyecto sin título",
        brief=raw.get("brief") or "",
        style=raw.get("style") or "lego",
        format=str(raw.get("format") or "9:16"),
        scenes=scenes,
    )


def draft_project(text: str) -> ProjectDraft:
    """Usa Claude para proponer un borrador de proyecto desde texto libre."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Instala el extra [apis] para usar Claude: uv sync --extra apis") from exc

    key = get_settings().require("anthropic_api_key", "borrador de proyecto")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=_DRAFT_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": _DRAFT_PROMPT.format(text=text)}],
    )
    return parse_draft(msg.content[0].text)
