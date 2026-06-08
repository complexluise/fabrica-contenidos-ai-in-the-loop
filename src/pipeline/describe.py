"""L10 - Ojos semanticos: Haiku describe y evalua cada plano del bundle (D-041).

Para editar sin editora (D-042) el agente necesita saber que hay en cada plano y
si sirve para el MENSAJE. `describe` extrae 1-3 frames del video limpio
(`export/media/<base>.mp4`) y le pide a Claude **Haiku** una descripcion +
evaluacion (usable / en-mensaje / roto), persistida en `descriptions.yaml`.

Haiku, no Opus: describir es alto volumen / bajo criterio (D-041). La decision
narrativa del corte la toma el agente (Opus), no este paso.

`describe_prompt`/`parse_description`/`_plano_context`/`_frame_times` son logica
pura (testeable); `describe_bundle` es I/O (ffmpeg + Haiku, smoke). Sin
ANTHROPIC_API_KEY degrada: escribe entradas vacias (permisivo, no rompe).
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import yaml

from .export import _manifest_planos, numbered
from .gate.frames import extract_frame
from .project import Project
from .settings import get_settings

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"  # ojos baratos (D-041); Opus decide el corte

_DESCRIBE_PROMPT = """Eres asistente de montaje de video. Mira el/los frame(s) de un plano ya
generado y describelo para un editor que NO lo ha visto. Importa mas el MENSAJE que el pulido.
Responde SOLO JSON: {{"description":"que se ve, 1-2 frases","on_message":0-1,"usable":true,"issues":[]}}
- description: que se ve (sujeto, accion, encuadre).
- on_message: 0-1, cuanto aporta este plano al mensaje/beat.
- usable: false SOLO si esta roto (artefactos graves, deforme, ilegible) y no deberia ir al corte.
- issues: lista corta de problemas (vacia si esta limpio).
Contexto del plano: {context}
"""


def describe_prompt(context: str) -> str:
    """El prompt de Haiku para un plano, con su contexto. Logica pura."""
    return _DESCRIBE_PROMPT.format(context=context)


def parse_description(text: str) -> dict:
    """Extrae la descripcion+evaluacion del JSON de Haiku. Tolerante (D-041).

    Mismo enfoque que `gate/fusion.py::parse_judge_metrics`: busca el primer/ultimo
    brace. Campos faltantes caen a defaults permisivos (usable=True).
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Respuesta sin JSON: {text[:200]}")
    data = json.loads(text[start : end + 1])
    return {
        "description": str(data.get("description", "")).strip(),
        "on_message": float(data.get("on_message", 0.0)),
        "usable": bool(data.get("usable", True)),
        "issues": [str(x) for x in (data.get("issues") or [])],
    }


def _plano_context(p: dict) -> str:
    """Contexto legible de un plano (beat/encuadre/voz/texto) para el prompt. Pura."""
    bits = []
    for label, key in (
        ("beat", "beat"), ("escena", "scene"), ("encuadre", "framing"),
        ("voz", "voiceover"), ("texto", "caption"),
    ):
        v = p.get(key)
        if isinstance(v, str) and v.strip():
            bits.append(f"{label}: {v.strip()}")
    return " | ".join(bits) or "(sin contexto)"


def _frame_times(duration: float) -> list[float]:
    """1-3 tiempos representativos segun la duracion del plano. Pura."""
    if duration <= 0:
        return [0.5]
    if duration < 2:
        return [round(duration / 2, 2)]
    if duration < 5:
        return [0.5, round(duration / 2, 2)]
    return [0.5, round(duration / 2, 2), round(max(0.5, duration - 0.5), 2)]


def _empty_entry(reason: str = "") -> dict:
    """Entrada permisiva cuando no se pudo evaluar (sin key / clip faltante / error)."""
    return {"description": "", "on_message": 0.0, "usable": True,
            "issues": [reason] if reason else []}


def _image_block(frame: Path) -> dict:
    """Bloque de imagen base64 para la API de Claude (patron de gate/vlm.py)."""
    ext = Path(frame).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    data = base64.standard_b64encode(Path(frame).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def _describe_clip(client, clip: Path, context: str, duration: float) -> dict:
    """Llama a Haiku con los frames del clip. I/O (smoke)."""
    blocks = [_image_block(extract_frame(clip, t)) for t in _frame_times(duration)]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": [*blocks, {"type": "text", "text": describe_prompt(context)}]}],
    )
    return parse_description(msg.content[0].text)


def describe_bundle(project: Project) -> Path:
    """Describe cada plano del bundle del ultimo run -> `descriptions.yaml`. I/O (smoke)."""
    run = project.latest_run()
    if run is None or not run.manifest_path.exists():
        raise RuntimeError(
            f"No hay runs para '{project.slug}'. Corre 'pipeline render {project.slug}' primero.")
    planos = numbered(_manifest_planos(run))
    if not planos:
        raise RuntimeError("El manifest del ultimo run no tiene planos.")
    media = project.dir / "export" / "media"
    if not media.exists():
        raise RuntimeError(
            f"No hay bundle de export. Corre 'pipeline export {project.slug}' primero.")

    client = None
    key = get_settings().anthropic_api_key
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
        except ImportError:  # pragma: no cover
            client = None
    if client is None:
        logger.warning("describe: sin ANTHROPIC_API_KEY (o sin paquete anthropic) -> "
                       "descripciones vacias (permisivo, nada se descarta).")

    out: list[dict] = []
    for p in planos:
        clip = media / f"{p['base']}.mp4"
        entry = {"n": p["n"], "base": p["base"],
                 "id": p.get("id") or p.get("scene") or p["base"]}
        if client is None:
            entry.update(_empty_entry())
        elif not clip.exists():
            entry.update(_empty_entry("clip ausente en el bundle"))
        else:
            try:
                entry.update(_describe_clip(client, clip, _plano_context(p),
                                            float(p.get("duration_s") or 0)))
            except Exception as exc:  # noqa: BLE001 - best-effort por plano
                logger.warning("describe: fallo en %s (%s); sin evaluar.", p["base"], exc)
                entry.update(_empty_entry(f"describe_error: {exc}"))
        out.append(entry)

    dest = project.dir / "descriptions.yaml"
    dest.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest
