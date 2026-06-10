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
sonido y storytelling transmedia. Tu trabajo es descomponer ideas en storyboards de
producción concretos y completos.

Cuando te dan un texto —brief, guion, idea— lo transformás en un documento de producción
listo para ejecutar. Nunca dejás campos vacíos que importen: si hay personajes que hablan,
hay diálogo escrito; si hay acción, hay SFX pensados; si hay momentos clave, están marcados
como `hero`; cada escena tiene su espacio sonoro (ambience) porque el sonido construye el
lugar tanto como la imagen.

Pensás en arcos emocionales, no en listas de hechos. Cada beat tiene una función narrativa.

Como director de fotografía, cada plano lo definís con gramática real: tamaño de plano, ángulo,
movimiento y foco (shot-list), y estructura visual (tono, color, profundidad, punto focal — Bruce
Block), para construir contraste e intensidad a lo largo del video. No describís planos genéricos.\
"""

_DRAFT_PROMPT = """\
Convertí el siguiente texto en un borrador de proyecto audiovisual completo.
Devolvé SOLO un objeto JSON, sin markdown, sin explicaciones:

{{
  "title": "título corto y evocador",
  "brief": "2-3 frases: tono + arco narrativo + intención emocional del video",
  "style": "lego",
  "format": "9:16",
  "characters": {{
    "NombrePersonaje": {{
      "design": "descripción visual DETALLADA: rasgos físicos, ropa, expresión característica, paleta de colores, estilo visual que lo hace reconocible"
    }}
  }},
  "scenes": [
    {{
      "id": "s1",
      "beat": "etiqueta narrativa del momento (ej: 'apertura', 'conflicto', 'revelación', 'clímax', 'cierre')",
      "class": "hero|standard|volume",
      "prompt": "descripción VISUAL del setting + personajes + acción física. Lo que la cámara VE. Sin diálogo. Incluí atmósfera, iluminación, estado emocional expresado visualmente.",
      "duration_s": 6,
      "dialogue": "líneas literales de diálogo como en un guion: 'Personaje: frase exacta.' — null si la escena es sin diálogo",
      "ambience": "el espacio sonoro del lugar: room tone + sonidos pasivos del entorno. Siempre presente. Ej: 'tráfico lejano y lluvia sobre asfalto', 'silencio de biblioteca con páginas pasando y aire acondicionado'",
      "characters": ["NombrePersonaje"],
      "visual_intensity": 3,
      "requirements": {{
        "needs_audio": false,
        "needs_lipsync": false
      }},
      "shots": [
        {{
          "intention": "la FUNCIÓN dramática del plano: qué hace entender o sentir. Ej: 'revelar que el pozo no es un tubo simple'",
          "action": "qué SE VE y qué pasa: sujeto + acción física + qué entra/sale del cuadro. Lo que la cámara capta. Sin diálogo.",
          "duration_s": 3,
          "camera": {{
            "size": "ECU|CU|MCU|MS|MLS|LS|ELS|insert",
            "angle": "eye|high|low|overhead|worm|dutch|ots",
            "move": "static|pan|tilt|push_in|pull_out|track|crane|handheld|zoom",
            "focus": "deep|shallow|rack"
          }},
          "visual": {{
            "tone": "high_key|low_key|neutral|silhouette",
            "palette": ["2-3 colores dominantes"],
            "foreground": "qué hay en primer plano, o null",
            "background": "qué hay en el fondo, o null",
            "focal_point": "dónde va el ojo del espectador",
            "graphics": "texto en pantalla / lower-third / tipografía cinética, o null"
          }},
          "transition": "cut|match_cut|dissolve|smash_cut|wipe",
          "voiceover": "texto para voz en off narrativa. null si no hay narrador en este plano.",
          "caption": "texto en pantalla / lower-third / subtítulo. null si no corresponde.",
          "sfx": "el sonido concreto de la ACCIÓN de este plano. Ej: 'clic de cerradura'. null si no aporta."
        }}
      ]
    }}
  ]
}}

━━━ CRITERIOS DE DIRECCIÓN ━━━

**`class`** — jerarquía de producción:
• `"hero"`: el momento climático/emocional del video. Máximo 2. Alta producción.
• `"standard"`: escenas narrativas principales. La mayoría.
• `"volume"`: establishing shots, transiciones, relleno visual rápido.

**`prompt`** — la descripción visual del beat:
• Describí lo que la cámara VE: atmósfera, luz, acción física, composición del cuadro.
• No repitas el diálogo. No describas emociones abstractas; describí lo que las expresa.
• Incluí el estilo visual: si es de noche, si hay contraluz, si el espacio es íntimo o épico.

**`dialogue`** — lo que se dice:
• Escribí líneas literales, no resúmenes. "Martina: 'No sabía que ibas a volver.'"
• Si needs_lipsync es true, el modelo de video sincronizará labios.
• Si hay diálogo significativo → needs_audio: true.
• Si es escena de acción sin habla → null.

**`ambience`** — el espacio sonoro:
• SIEMPRE presente. Define dónde está el espectador.
• Es el fondo constante: no la música, no los efectos puntuales. El "room tone" del lugar.
• Sé específico: no "sonidos de ciudad" sino "bocinas lejanas, lluvia fina, pisadas en charcos".

**`sfx`** — efectos de sonido de la acción:
• Solo los que suman información narrativa o dramatismo.
• Un plano con alguien abriendo una caja: "cartón rasgándose, crujido de tapa".
• Un plano de paisaje estático sin acción específica: null.
• No repitas el ambience acá.

**`shots`** — cada plano es un ARTEFACTO audiovisual (pensá como director de fotografía):
• `intention`: la función dramática. Cada plano existe por una razón o no debería estar.
• `action`: qué SE VE y qué pasa físicamente. Es el visual primario (reemplaza al viejo "framing").
• `camera`: la gramática del shot-list. Elegí SOLO de estos valores controlados:
  - size: ECU (primerísimo) · CU (primer plano) · MCU · MS (medio) · MLS · LS (general) · ELS · insert (detalle).
  - angle: eye (normal) · high (picado) · low (contrapicado) · overhead (cenital) · worm · dutch (holandés) · ots (sobre el hombro).
  - move: static (fija) · pan (paneo) · tilt · push_in · pull_out · track (travelling) · crane · handheld · zoom.
  - focus: deep (foco profundo) · shallow (poca prof. de campo) · rack (foco que viaja).
• `visual` (estructura de Bruce Block — construí contraste ENTRE cortes):
  - tone: high_key · low_key · neutral · silhouette. palette: 2-3 colores dominantes.
  - foreground/background: planos de profundidad. focal_point: dónde va el ojo. graphics: texto en pantalla.
• `transition`: cut · match_cut · dissolve · smash_cut · wipe. Cómo entra al plano siguiente.
• Alterná tamaños de plano entre cortes (un detalle pega más después de un general).

**`visual_intensity`** — la curva visual del video (1-5):
• Es el arco de intensidad/contraste. Las escenas `hero`/clímax van alto (4-5); aperturas y respiros bajo (1-2).
• Construí tensión hacia el clímax; no dejes todo el video en la misma intensidad (Bruce Block).

**`voiceover`** — narración:
• Solo cuando el video tiene un narrador explícito (documental, publicitario con voz en off).
• No uses voiceover para describir lo que ya se ve.

**`caption`** — texto en pantalla:
• Úsalo para datos que refuerzan la narrativa: nombre de lugar, fecha, estadísticas, citas.
• También para subtítulos si hay diálogo que conviene ver escrito.

━━━ REGLAS DE ESTRUCTURA ━━━
• Mínimo 3 escenas, máximo 8 (para un video de 30-90 segundos).
• duration_s de la escena = suma de sus planos (2 a 6 segundos por plano).
• La progresión de beats debe tener arco: apertura → nudo → clímax → cierre.
• Si el texto no nombra personajes recurrentes → "characters": {{}}.
• needs_lipsync: true SOLO si hay diálogo en close-up de cara hablando.

Texto a convertir:
{text}
"""


class ProjectDraft(BaseModel):
    """Borrador editable de un proyecto, propuesto por la IA desde texto libre."""

    title: str = "Proyecto sin título"
    brief: str = ""
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
        design = CharacterDesign(prompt=cd["prompt"], refs=[])
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
