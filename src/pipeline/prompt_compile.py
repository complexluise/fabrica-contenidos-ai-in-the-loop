"""L1.5 - Prompt visual derivado de la narrativa (D-046).

El Storyboard es la fuente de verdad (D-045): el humano firma la HISTORIA
(beat, dialogo, ambience, personajes). El prompt visual `scene.prompt` —lo que
de verdad entra a generar el keyframe (`keyframe.build_styled_prompt`)— se
COMPILA desde esa narrativa, no se mantiene a mano en paralelo. Asi se cierra el
hueco de D-045: el humano firma una historia y la IA genera desde ESA historia,
no desde un prompt viejo que quedo a la deriva.

Haiku traduce el beat narrativo a una descripcion visual de lo que la camara VE;
sin ANTHROPIC_API_KEY cae a una concatenacion determinista (degrada, no rompe —
mismo patron que `describe.py` / `gate/vlm.py`). Haiku, no Opus: traducir
narrativa->visual es alto volumen, bajo criterio (D-041).

`narrative_brief` y `_deterministic_prompt` son logica pura (testeable);
`compile_prompt` hace la llamada a Haiku (I/O, smoke).
"""

from __future__ import annotations

import logging

from .contracts import Camera, Scene, Shot, Visual
from .project import Character, CharacterDesign
from .settings import get_settings

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"  # traduccion narrativa->visual: alto volumen, bajo criterio (D-041)

_SYSTEM = """\
Sos director de fotografia. Traducis un beat narrativo (en español) a una descripcion
VISUAL concreta de lo que la camara VE: setting, personajes, accion fisica, luz,
atmosfera, composicion del cuadro. No repetis el dialogo. No describis emociones
abstractas; describis lo que las expresa en imagen.
IMPORTANTE: respondé EN INGLÉS (este prompt alimenta el modelo de imagen, D-050),
UNA sola frase densa, sin comillas ni preámbulo."""

_PROMPT = """\
Traducí esta escena a una descripción visual EN INGLÉS para un modelo de imagen.
Devolvé SOLO la descripción en inglés, sin comillas ni explicación.

{brief}
"""


# --- Composicion del plano (D-047): gramatica/estructura -> lenguaje natural ---
# Mapas del vocabulario controlado a frases que el modelo de imagen entiende.
# En ingles a proposito: los modelos generativos rinden mejor en ingles, igual
# que los `prompt_template` de los estilos.

_SIZE = {
    "ECU": "extreme close-up", "CU": "close-up", "MCU": "medium close-up",
    "MS": "medium shot", "MLS": "medium long shot", "LS": "long shot",
    "ELS": "extreme long shot", "insert": "insert detail shot",
}
_ANGLE = {
    "eye": "eye-level angle", "high": "high angle", "low": "low angle",
    "overhead": "overhead bird's-eye angle", "worm": "worm's-eye angle",
    "dutch": "dutch (canted) angle", "ots": "over-the-shoulder angle",
}
_MOVE = {
    "static": "static camera", "pan": "panning", "tilt": "tilting",
    "push_in": "slow push-in", "pull_out": "pull-out", "track": "tracking shot",
    "crane": "crane move", "handheld": "handheld", "zoom": "zoom",
}
_FOCUS = {"deep": "deep focus", "shallow": "shallow depth of field", "rack": "rack focus"}
_TONE = {
    "high_key": "high-key lighting", "low_key": "low-key lighting",
    "neutral": "neutral lighting", "silhouette": "silhouette lighting",
}


def camera_phrase(cam: Camera) -> str:
    """Gramatica de camara para el KEYFRAME (imagen FIJA): tamano/angulo/foco/lente.

    NO incluye el movimiento: una imagen fija no tiene 'push-in' (D-048/A1). El
    movimiento vive en `motion_phrase` y alimenta el prompt de VIDEO. Pura."""
    if cam.size == "MS" and cam.angle == "eye" and cam.focus == "deep" and not cam.lens_mm:
        return ""  # camara fija neutra -> no aporta al prompt
    bits = [_SIZE.get(cam.size, ""), _ANGLE.get(cam.angle, "")]
    if cam.focus != "deep":
        bits.append(_FOCUS.get(cam.focus, ""))
    if cam.lens_mm:
        bits.append(f"{cam.lens_mm}mm lens")
    return ", ".join(b for b in bits if b)


def motion_phrase(cam: Camera) -> str:
    """Movimiento de camara para el VIDEO (D-048/A1). Vacio si la camara es estatica."""
    return "" if cam.move == "static" else _MOVE.get(cam.move, "")


def visual_phrase(vis: Visual) -> str:
    """La estructura visual (Block) como frase. Pura. Vacia si no hay nada."""
    if vis.is_empty():
        return ""
    bits: list[str] = []
    if vis.tone:
        bits.append(_TONE.get(vis.tone, ""))
    if vis.palette:
        bits.append("palette " + ", ".join(vis.palette))
    depth = [p for p in (vis.foreground, vis.midground, vis.background) if p]
    if depth:
        bits.append("depth: " + "; ".join(depth))
    if vis.focal_point:
        bits.append(f"focal point on {vis.focal_point}")
    if vis.line:
        bits.append(vis.line)
    if vis.rhythm:
        bits.append(vis.rhythm)
    if vis.graphics:
        bits.append(f'on-screen graphics: "{vis.graphics}"')
    return ", ".join(b for b in bits if b)


def _shot_base(shot: Shot) -> str:
    """La descripcion primaria del plano: `action`, o el `framing` legacy. Pura."""
    return (shot.action or "").strip() or (shot.framing or "").strip()


def compose_keyframe_prompt(shot: Shot) -> str:
    """Texto para el KEYFRAME (imagen fija): que se ve + camara fija + estructura
    visual de Block. SIN movimiento (D-048/A1). Reemplaza a compose_shot_visual."""
    parts = [_shot_base(shot), camera_phrase(shot.camera), visual_phrase(shot.visual)]
    return ". ".join(p for p in parts if p)


def compose_video_prompt(shot: Shot) -> str:
    """Texto para el VIDEO (movimiento/accion). El keyframe entra como `init_image`,
    asi que aca importa el MOVIMIENTO y la accion, no re-describir la composicion
    fija (D-048/A1). Pura."""
    parts = [_shot_base(shot), motion_phrase(shot.camera)]
    return ", ".join(p for p in parts if p)


# Cómo entra la cámara al plano según la transición de ENTRADA (D-060): en cortes
# duros el encuadre se libera; en transiciones suaves se mantiene cercano al previo.
_REFRAME_BY_TRANSITION = {
    "cut": "a hard cut: completely new framing and camera position",
    "smash_cut": "an abrupt smash cut: drastically different framing",
    "wipe": "a wipe: new framing",
    "match_cut": "a match cut: closely matched composition to the previous moment",
    "dissolve": "a soft dissolve: similar framing flowing from the previous moment",
    None: "a continuous flow from the previous moment, same framing language",
}


def compose_start_pose_prompt(shot: Shot, transition_in: str | None = None) -> str:
    """Texto para el START-STILL del plano (D-060): la pose de APERTURA.

    Describe el estado donde el movimiento APENAS COMIENZA (no el pico — el pico
    es el destino) y cómo se reencuadra según la transición de entrada. El still
    se genera EDITANDO el destino del plano anterior → continuidad de elementos
    a través de todo el film, incluso en cortes. Pura."""
    base = _shot_base(shot)
    reframe = _REFRAME_BY_TRANSITION.get(transition_in, _REFRAME_BY_TRANSITION[None])
    parts = [
        f"One beat later, entering the next shot via {reframe}",
        f"the OPENING composition of: {base}" if base else "",
        "the action just beginning, NOT yet at its peak",
        camera_phrase(shot.camera),
    ]
    return ". ".join(p for p in parts if p)


# Alias retrocompatible: el "visual del plano" es el del keyframe (la imagen fija).
compose_shot_visual = compose_keyframe_prompt


def compose_character_prompt(design: CharacterDesign) -> str:
    """Ensambla el artefacto de personaje (D-049/B2) en el prompt de casting:
    prompt base + rasgos fisicos + vestuario + paleta + expresion. Pura."""
    parts = [(design.prompt or "").strip()]
    if design.physical:
        parts.append(design.physical.strip())
    if design.wardrobe:
        parts.append(design.wardrobe.strip())
    if design.palette:
        parts.append("color palette: " + ", ".join(design.palette))
    if design.expression:
        parts.append(design.expression.strip())
    return ", ".join(p for p in parts if p)


def narrative_brief(scene: Scene, characters: dict[str, Character] | None = None) -> str:
    """Texto fuente (la narrativa de la escena) que alimenta la compilacion. Pura."""
    characters = characters or {}
    bits: list[str] = []
    if scene.beat:
        bits.append(f"Beat: {scene.beat.strip()}")
    if scene.characters:
        who: list[str] = []
        for name in scene.characters:
            ch = characters.get(name)
            design = ch.design.prompt.strip() if ch and ch.design else ""
            who.append(f"{name} ({design})" if design else name)
        bits.append("Personajes: " + ", ".join(who))
    if scene.dialogue:
        bits.append(f"Diálogo (contexto, no lo describas literal): {scene.dialogue.strip()}")
    if scene.ambience:
        bits.append(f"Lugar/ambiente: {scene.ambience.strip()}")
    return "\n".join(bits) or "(sin narrativa; describí un plano neutro y atmosférico)"


def _deterministic_prompt(scene: Scene, characters: dict[str, Character] | None = None) -> str:
    """Fallback sin LLM: concatena los campos narrativos en algo usable. Pura."""
    parts: list[str] = []
    if scene.beat:
        parts.append(scene.beat.strip())
    if scene.characters:
        parts.append(", ".join(scene.characters))
    if scene.ambience:
        parts.append(scene.ambience.strip())
    return ", ".join(parts) or (scene.prompt or scene.id)


def compile_prompt(scene: Scene, characters: dict[str, Character] | None = None) -> str:
    """Compila el prompt visual desde la narrativa. Haiku; sin key, deterministico."""
    key = get_settings().anthropic_api_key
    if not key:
        logger.warning("prompts: sin ANTHROPIC_API_KEY -> prompt deterministico (degradado).")
        return _deterministic_prompt(scene, characters)
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        logger.warning("prompts: sin paquete anthropic -> prompt deterministico.")
        return _deterministic_prompt(scene, characters)
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=_SYSTEM,
        messages=[{"role": "user",
                   "content": _PROMPT.format(brief=narrative_brief(scene, characters))}],
    )
    text = (msg.content[0].text or "").strip()
    return text or _deterministic_prompt(scene, characters)


def sync_scene_prompt(scene: Scene, characters: dict[str, Character] | None = None) -> Scene:
    """Recompila el prompt y lo marca en-sintonia (auto, hash actualizado). Muta y devuelve."""
    scene.prompt = compile_prompt(scene, characters)
    scene.prompt_src_hash = scene.narrative_hash()
    scene.prompt_manual = False
    return scene


def mark_synced(scene: Scene) -> Scene:
    """Marca el prompt ACTUAL como en-sintonia sin recompilar (p.ej. tras el draft de author)."""
    scene.prompt_src_hash = scene.narrative_hash()
    scene.prompt_manual = False
    return scene


def compose_ref_map(source_label: str | None = None, characters: list[str] | None = None) -> str:
    """Mapa de referencias CON NOMBRE para los modelos de edición (D-067). Pura.

    Kontext/nano-banana reciben una pila de imágenes anónimas: sin este mapa no
    saben cuál es el set, cuál es la cara de quién — de ahí los vestuarios
    cruzados. El orden del mapa DEBE coincidir con el orden real de ref_images."""
    lines = ["Reference images, in order:"]
    i = 1
    if source_label:
        lines.append(f"image {i} = {source_label} (continue this exact look and set);")
        i += 1
    for name in characters or []:
        lines.append(f"image {i} = {name} (keep this EXACT face and outfit for {name});")
        i += 1
    return " ".join(lines)
