"""L2 - Clasificador de escenas: hero | standard | volume.

Hibrido: reglas deterministas para lo obvio (gratis) + Claude para lo ambiguo.
Cada decision se podria loguear para entrenar un clasificador barato a futuro.
El cuello de botella real del pipeline -> aqui importa la calibracion.
"""

from __future__ import annotations

from .contracts import Scene, SceneClass
from .settings import get_settings

# Palabras que sugieren relleno/B-roll (volumen).
_VOLUME_HINTS = ("b-roll", "establishing", "transicion", "paisaje", "ambiente", "relleno")


def classify_by_rules(scene: Scene) -> SceneClass | None:
    """Reglas deterministas. Devuelve None si la escena es ambigua."""
    # Dialogo o audio sincronizado -> hero (necesita Veo).
    if scene.dialogue or scene.requirements.needs_audio:
        return "hero"
    # Multiples personajes nombrados -> consistencia critica -> standard.
    if len(scene.characters) >= 2:
        return "standard"
    # Pistas de relleno o tomas sin personajes -> volumen.
    text = scene.prompt.lower()
    if not scene.characters or any(h in text for h in _VOLUME_HINTS):
        return "volume"
    return None


def classify_by_llm(scene: Scene) -> SceneClass:  # pragma: no cover - I/O externo
    """Arbitra escenas ambiguas con Claude. Fallback determinista: standard."""
    key = get_settings().anthropic_api_key
    if not key:
        return "standard"
    try:
        import anthropic
    except ImportError:
        return "standard"

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=10,
        messages=[
            {
                "role": "user",
                "content": (
                    "Clasifica esta toma en una palabra: hero (marca/dialogo/clave), "
                    "standard (normal con personajes) o volume (relleno/b-roll). "
                    f"Toma: {scene.prompt}. Responde solo la palabra."
                ),
            }
        ],
    )
    answer = msg.content[0].text.strip().lower()
    return answer if answer in ("hero", "standard", "volume") else "standard"


def classify(scene: Scene) -> SceneClass:
    """Pipeline de clasificacion: reglas primero, LLM para lo gris."""
    by_rules = classify_by_rules(scene)
    if by_rules is not None:
        return by_rules
    return classify_by_llm(scene)
