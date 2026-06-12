"""L1 - Autoría asistida: texto libre -> borrador de proyecto (D-033, Fase 2 app).

El Checkpoint #1 de [D-021] hecho interfaz: la persona pega/sube un texto y la IA
**propone** un borrador completo (título, brief, escenas con planos, diálogo, sonido,
música); luego la persona lo **edita y firma** en el storyboard. La IA descompone;
la persona decide.

`parse_draft` es lógica pura (testeable: parseo del JSON del LLM); `draft_project`
es I/O (Claude, smoke). El borrador se materializa con `project.write_spec`.
"""

from __future__ import annotations

import json
from typing import get_args

from pydantic import BaseModel, Field

from .contracts import (
    CameraAngle,
    CameraMove,
    FocusDepth,
    Scene,
    ShotSize,
    ToneKey,
    Transition,
)
from .project import Character, CharacterDesign
from .settings import get_settings

_DRAFT_MODEL = "claude-opus-4-8"

# Persona del sistema: director-guionista con formación completa.
_DRAFT_SYSTEM = """\
Sos un director-guionista audiovisual con formación en narrativa visual, diseño de
sonido y fotografía. Transformás un texto en un documento de producción concreto y completo.
Nunca dejás vacíos los campos que importan: si hablan, hay diálogo; si hay acción, hay SFX;
los momentos clave van como `hero`; cada escena tiene su espacio sonoro (ambience).

━━━ IDIOMA (regla dura) ━━━
• Lo que la audiencia VE u OYE va en ESPAÑOL: title, brief, beat, intention, dialogue,
  voiceover, caption y el texto en pantalla (visual.graphics).
• Lo que alimenta a los MODELOS de IA (imagen, video, audio) va en INGLÉS: prompt, action,
  los campos de `visual` (foreground/midground/background/focal_point/line/rhythm/palette),
  ambience, sfx y el diseño de personaje (prompt/physical/wardrobe/palette/expression).
  Los valores de `camera`, `tone` y `transition` son tokens fijos (ni ES ni EN).

━━━ CÓMO PENSÁS LA IMAGEN ━━━
• Cada plano es un ARTEFACTO: tamaño/ángulo/movimiento/foco (shot-list) + estructura visual
  (tono, color, profundidad, punto focal — Bruce Block). No describís planos genéricos.
• El KEYFRAME es una imagen FIJA: en `action` describís lo que se VE (composición), NO el
  movimiento. El movimiento de cámara vive en `camera.move` y es cosa del VIDEO.
• Los planos de una escena se ENCADENAN (cada plano se genera EDITANDO el anterior): comparten
  set, props, personajes y look. Escribilos como CONTINUACIONES (qué cambia: encuadre, acción,
  foco), no como escenas nuevas. El plano 1 es el ancla de la escena.
• Construís un ARCO de intensidad visual hacia el clímax (visual_intensity), con contraste
  entre cortes (alterná tamaños de plano).\
"""

_DRAFT_PROMPT = """\
Convertí el siguiente texto en un borrador de proyecto audiovisual completo.
Devolvé SOLO un objeto JSON, sin markdown, sin explicaciones. Cada campo lleva [ES] (español,
lo ve/oye la audiencia) o [EN] (inglés, alimenta a un modelo de IA):

{{
  "title": "[ES] título corto y evocador",
  "brief": "[ES] 2-3 frases: tono + arco narrativo + intención emocional",
  "world": "[EN] la BIBLIA del mundo: UNA descripción canónica del set/luz/clima/paleta que comparten TODAS las escenas (2-3 frases). Viaja a cada prompt: no la repitas en los prompts de escena.",
  "music_prompt": "[EN] la cama musical del film: género/tempo/instrumentación/arco emocional (1-2 frases). null si la pieza no lleva música.",
  "style": "lego",
  "format": "9:16",
  "characters": {{
    "NombrePersonaje": {{
      "design": {{
        "prompt": "[EN] visual description that makes the character recognizable (1-2 sentences)",
        "physical": "[EN] distinctive physical traits: face, hair, body",
        "wardrobe": "[EN] signature wardrobe",
        "palette": ["[EN] 2-3 character colors"],
        "expression": "[EN] defining gesture/expression"
      }}
    }}
  }},
  "scenes": [
    {{
      "id": "s1",
      "beat": "[ES] etiqueta narrativa del momento (ej: 'apertura', 'revelación', 'clímax', 'cierre')",
      "class": "hero|standard|volume",
      "prompt": "[EN] scene BASE for the image model: setting + characters + atmosphere + lighting. The fixed look the scene shares. No dialogue.",
      "duration_s": 6,
      "dialogue": "[ES] líneas literales de guion: 'Personaje: frase exacta.' — null si no hay diálogo",
      "ambience": "[EN] room tone of the place for the audio model: passive ambient sound. Always present. Ej: 'distant traffic and light rain', 'quiet studio room hum'",
      "characters": ["NombrePersonaje"],
      "visual_intensity": 3,
      "requirements": {{ "needs_audio": false, "needs_lipsync": false }},
      "shots": [
        {{
          "intention": "[ES] la FUNCIÓN dramática del plano: qué hace entender o sentir. Solo la lee el humano.",
          "action": "[EN] what is SEEN (still composition) + what physically happens: subject + action + what enters/leaves frame. NO camera movement here.",
          "duration_s": 3,
          "camera": {{
            "size": "ECU|CU|MCU|MS|MLS|LS|ELS|insert",
            "angle": "eye|high|low|overhead|worm|dutch|ots",
            "move": "static|pan|tilt|push_in|pull_out|track|crane|handheld|zoom",
            "focus": "deep|shallow|rack"
          }},
          "visual": {{
            "tone": "high_key|low_key|neutral|silhouette",
            "palette": ["[EN] 2-3 dominant colors"],
            "foreground": "[EN] what is in the foreground, or null",
            "background": "[EN] what is in the background, or null",
            "focal_point": "[EN] where the viewer's eye goes",
            "graphics": "[ES] el TEXTO que aparece en pantalla (lower-third / tipografía), o null"
          }},
          "transition": "cut|match_cut|dissolve|smash_cut|wipe",
          "voiceover": "[ES] texto de voz en off. null si no hay narrador en este plano.",
          "caption": "[ES] texto en pantalla / subtítulo. null si no corresponde.",
          "sfx": "[EN] the concrete sound of THIS shot's action for the audio model. Ej: 'lock click'. null si no aporta."
        }}
      ]
    }}
  ]
}}

━━━ CRITERIOS DE DIRECCIÓN ━━━

**Idioma:** respetá [ES]/[EN] al pie de la letra. Un `action` o `prompt` en español, o un `caption`
en inglés, es un ERROR. Los enums (camera/tone/transition) van tal cual.

**`class`** — jerarquía: `hero` (clímax, máx 2) · `standard` (la mayoría) · `volume` (transiciones).

**`world`** (la biblia, [EN]) — el universo se describe UNA vez y viaja a cada prompt (ingeniería de
contexto, D-067). Los `prompt` de escena NO re-describen el set: solo lo que esa escena AGREGA.

**`prompt`** (scene base, [EN]) — lo que la ESCENA agrega al mundo: qué personajes, qué pasa, qué
atmósfera puntual. Sin re-describir el set (eso vive en `world`), sin diálogo, sin cámara.

**ACCIONES EJECUTABLES** — escribí `action` que un modelo de video PUEDE hacer: movimientos físicos
simples y de UN beat (caer, girar, extender, chocar), siluetas fuertes, causa visible. NO escribas
interacciones finas de objetos ("atrapa la palabra y el brillo muere entre sus dedos"): el modelo
improvisa y rompe la coherencia. El impacto emocional va al CORTE y al SONIDO, no a la actuación.

**`shots`** — cada plano es un ARTEFACTO (pensá como director de fotografía):
• `intention` [ES]: la función dramática. Cada plano existe por una razón.
• `action` [EN]: lo que se VE (composición fija) + qué pasa. SIN movimiento de cámara (eso es video).
• `camera` (tokens): size ECU·CU·MCU·MS·MLS·LS·ELS·insert; angle eye·high·low·overhead·worm·dutch·ots;
  move static·pan·tilt·push_in·pull_out·track·crane·handheld·zoom; focus deep·shallow·rack.
  El `move` es el movimiento del VIDEO (el keyframe es fijo).
• `visual` (Bruce Block, [EN] salvo graphics): tone (token) · palette · foreground/background ·
  focal_point. `graphics` [ES] = el texto literal en pantalla.
• `transition` (token): cómo entra al plano siguiente.

**ENCADENADO** — los planos de una escena se generan EDITANDO al anterior: comparten set, props,
personajes y look. Escribí cada plano como CONTINUACIÓN (qué cambia: encuadre, acción, foco), no
como una escena nueva. Alterná tamaños de plano entre cortes para dar contraste.

**`visual_intensity`** (1-5) — el arco de intensidad: `hero`/clímax alto (4-5), aperturas/respiros
bajo (1-2). Construí tensión hacia el clímax; no dejes todo plano en la misma intensidad (Block).

**COBERTURA (découpage)** — pensá la cobertura como un director de fotografía:
• Una escena `hero` lleva 3-5 planos: establecimiento → medio/acción → detalle (insert) o REACCIÓN.
  El clímax merece cobertura; un hero de 1 plano lo desperdicia.
• DIÁLOGO entre dos personajes → plano/contraplano (alterná quién ocupa el cuadro; usa `ots`).
• `standard` 2-3 planos; `volume` puede ser 1. Nunca repitas tamaño+ángulo en dos cortes seguidos.
• DIRECCIÓN DE PANTALLA (eje/180°): si un personaje mira o se mueve hacia la derecha, mantené esa
  dirección en los planos siguientes de la escena (no cruces el eje sin un plano neutro).

**DURACIÓN (es de EDICIÓN, no de facturación — D-068)** — `duration_s` es lo que el plano dura EN
EL CORTE: acción 1.5-2.5s (cortes rápidos, impact frames), diálogo lo que la línea necesite
(~2.5 palabras/segundo), respiros 3-4s. El proveedor genera bloques de ~5s igual: el sobrante es
COBERTURA, no desperdicio. No alargues planos para "aprovechar el bloque" — eso mata el ritmo.

**TRANSICIONES (semántica)** — la transición define cómo ARRANCA el plano siguiente:
• `cut` (default): nueva composición libre. • `match_cut`: SOLO si los dos planos comparten
  composición/forma (la promesa visual debe cumplirse). • `dissolve`: paso de tiempo o calma.
• `smash_cut`: contraste violento (de quieto a caos). No uses match_cut/dissolve por decorar.

**Sonido** — cómo se OYE cada cosa en este pipeline (importa para que no quede mudo):
• `dialogue` [ES] a nivel ESCENA: las líneas literales del guion ("Personaje: frase"). Alimenta el
  guion de export; NO es lo que se escucha por sí solo.
• `voiceover` [ES] en el PLANO que entrega la línea: es lo que el TTS DOBLA y se ESCUCHA. **Si un
  personaje habla, esa misma línea va TAMBIÉN en el `voiceover` del plano** (sin el prefijo "Personaje:").
  Una línea hablada que solo está en `dialogue` y no en ningún `voiceover` queda MUDA (solo texto).
  Sirve igual para narrador en off. No narres lo que ya se ve.
• `voice_id` [token]: por escena, y TAMBIÉN por plano (D-065) — si en una misma escena hablan dos
  personajes (plano/contraplano), cada plano que habla lleva el `voice_id` de SU hablante. El humano
  configura los ids de voz; vos dejá el campo presente con un placeholder del nombre del personaje.
• `ambience` [EN] (room tone, siempre presente) y `sfx` [EN] (solo si suma) — el sonido del lugar y
  de la acción los agrega un paso de audio (V2A) sobre el clip; van SIEMPRE que correspondan.
• `needs_audio`: dejalo en `false` (default). NO es como se obtiene diálogo/SFX acá: solo sirve para
  un provider de audio NATIVO sincronizado (raro). Prenderlo sin un provider así HACE FALLAR la escena.
• `needs_lipsync`: `false` salvo que de verdad quieras labios sincronizados; ten en cuenta que FIJA
  el provider a uno con esa capacidad.

Ejemplo de una línea hablada (se ve Y se escucha):
  escena: `dialogue: "Cepeda: Conversemos."`
  plano que la dice: `voiceover: "Conversemos."`, `caption: "Conversemos."`

━━━ REGLAS DE ESTRUCTURA ━━━
• 3 a 8 escenas (video de 30-90s). duration_s de la escena = suma de sus planos (2-6s por plano).
• Arco de beats: apertura → nudo → clímax → cierre.
• Si el texto no nombra personajes recurrentes → "characters": {{}}.

Texto a convertir:
{text}
"""


class ProjectDraft(BaseModel):
    """Borrador editable de un proyecto, propuesto por la IA desde texto libre."""

    title: str = "Proyecto sin título"
    brief: str = ""
    world: str = ""
    music_prompt: str = ""
    style: str = "lego"
    format: str = "9:16"
    characters: dict[str, Character] = Field(default_factory=dict)
    scenes: list[Scene] = Field(default_factory=list)

    def to_spec(self, slug: str):
        """Convierte el borrador en un ProjectSpec listo para `write_spec`."""
        from .project import ProjectSpec

        return ProjectSpec(
            slug=slug,
            style=self.style,
            format=self.format,
            scenes=self.scenes,
            characters=self.characters,
            title=self.title,
            brief=self.brief,
            world=self.world or None,
            music_prompt=self.music_prompt or None,
        )


_CAM_ENUMS = {
    "size": set(get_args(ShotSize)), "angle": set(get_args(CameraAngle)),
    "move": set(get_args(CameraMove)), "focus": set(get_args(FocusDepth)),
}
_TONES = set(get_args(ToneKey))
_TRANSITIONS = set(get_args(Transition))


def _coerce_camera(raw) -> dict | None:
    """Mantiene solo los enums VÁLIDOS de camera (D-047); descarta valores inventados
    por el LLM para que la validación nunca reviente el borrador entero."""
    if not isinstance(raw, dict):
        return None
    out = {k: raw[k] for k, allowed in _CAM_ENUMS.items()
           if isinstance(raw.get(k), str) and raw[k] in allowed}
    if isinstance(raw.get("lens_mm"), (int, float)):
        out["lens_mm"] = int(raw["lens_mm"])
    return out or None


def _coerce_visual(raw) -> dict | None:
    """Sanea el bloque visual (Block): tono enum válido, palette lista, resto strings."""
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    if isinstance(raw.get("tone"), str) and raw["tone"] in _TONES:
        out["tone"] = raw["tone"]
    if isinstance(raw.get("palette"), list):
        pal = [str(x).strip() for x in raw["palette"] if str(x).strip()]
        if pal:
            out["palette"] = pal
    for k in ("foreground", "midground", "background", "focal_point", "line", "rhythm", "graphics"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out or None


def _sanitize_shot(sh: dict) -> dict:
    """Normaliza un plano del LLM: enums controlados de camera/visual/transition (D-047)."""
    sh = dict(sh)
    cam = _coerce_camera(sh.get("camera"))
    sh["camera"] = cam if cam else None
    if sh["camera"] is None:
        sh.pop("camera")
    vis = _coerce_visual(sh.get("visual"))
    sh["visual"] = vis if vis else None
    if sh["visual"] is None:
        sh.pop("visual")
    if not (isinstance(sh.get("transition"), str) and sh["transition"] in _TRANSITIONS):
        sh.pop("transition", None)
    return sh


def _scene_from_raw(raw: dict, idx: int) -> Scene:
    """Normaliza una escena del LLM en un Scene válido (rellena lo que falte)."""
    s = dict(raw)
    s.setdefault("id", f"s{idx + 1}")
    if s.get("shots"):  # D-047: sanear enums de cada plano antes de validar
        s["shots"] = [_sanitize_shot(sh) for sh in s["shots"]]
    # visual_intensity: clamp 1-5 o descartar.
    vi = s.get("visual_intensity")
    if isinstance(vi, (int, float)):
        s["visual_intensity"] = max(1, min(5, int(vi)))
    else:
        s.pop("visual_intensity", None)
    # duration_s obligatorio (>0): derivar de los planos o caer a un default.
    if not s.get("duration_s"):
        shots = s.get("shots") or []
        total = sum(float(sh.get("duration_s") or 0) for sh in shots)
        s["duration_s"] = total or 5
    # Usar model_validate para manejar el alias "class" -> class_ correctamente.
    scene = Scene.model_validate(s)
    # D-046: el prompt del draft nace DE la narrativa propuesta -> sellar como
    # en-sintonia para que el storyboard no aparezca todo "desactualizado".
    scene.prompt_src_hash = scene.narrative_hash()
    return scene


def _character_from_raw(name: str, raw) -> Character:
    """Normaliza un personaje del LLM. `design` puede venir como string (la
    descripción) o como objeto `{"prompt": ..., "refs": [...]}`. Las refs quedan
    vacías: el humano las sube luego (banco de personajes, D-019)."""
    design = None
    cd = (raw or {}).get("design") if isinstance(raw, dict) else None
    if isinstance(cd, str) and cd.strip():
        design = CharacterDesign(prompt=cd.strip(), refs=[])
    elif isinstance(cd, dict) and cd.get("prompt"):
        # D-049/B2: artefacto de personaje (campos opcionales, tolerante).
        design = CharacterDesign(
            prompt=cd["prompt"], refs=[],
            physical=cd.get("physical") or None,
            wardrobe=cd.get("wardrobe") or None,
            palette=[str(x).strip() for x in (cd.get("palette") or []) if str(x).strip()],
            expression=cd.get("expression") or None,
        )
    return Character(name=name, design=design)


def _parse_characters(raw) -> dict[str, Character]:
    """Acepta el dict `{nombre: {design}}` (instruido) o una lista `[{name,...}]`."""
    if isinstance(raw, dict):
        return {name: _character_from_raw(name, c) for name, c in raw.items()}
    if isinstance(raw, list):
        out: dict[str, Character] = {}
        for c in raw:
            name = (c or {}).get("name") if isinstance(c, dict) else None
            if name:
                out[name] = _character_from_raw(name, c)
        return out
    return {}


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
        characters=_parse_characters(raw.get("characters")),
        scenes=scenes,
    )


def draft_project(text: str) -> ProjectDraft:
    """Usa Claude para proponer un borrador de proyecto desde texto libre."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Instala el extra [apis] para usar Claude: uv sync --extra apis"
        ) from exc

    key = get_settings().require("anthropic_api_key", "borrador de proyecto")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=_DRAFT_MODEL,
        max_tokens=8000,
        system=_DRAFT_SYSTEM,
        messages=[{"role": "user", "content": _DRAFT_PROMPT.format(text=text)}],
    )
    return parse_draft(msg.content[0].text)
