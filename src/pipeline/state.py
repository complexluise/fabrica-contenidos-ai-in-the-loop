"""Core: estado DERIVADO del proyecto (D-032).

El avance de un proyecto NO se almacena: se calcula desde los artefactos en disco
(casting.yaml, selections.yaml, candidates.yaml, runs/, export/) mas el
prerequisito de claves. Asi el estado nunca miente -- bumpear un seed o borrar un
archivo se refleja solo, sin un campo `status` que quede desincronizado.

`compute_stage` es la maquina de estados pura (los guards viven aca: no se
renderiza sin encuadres elegidos, no se empaqueta sin render). `derive_state` es
la lectura barata de disco. Fuente UNICA de verdad para la UI (server + front).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

from .project import Project, ProjectSpec, _resolve_under


class Stage(str, Enum):
    """El primer paso pendiente del bucle. COMPLETO = no queda nada por hacer."""

    SIN_CLAVES = "sin_claves"  # falta FAL_KEY (prerequisito de todo)
    GUION = "guion"            # storyboard sin firmar (D-035)
    CASTING = "casting"        # hay personajes con design: sin cara elegida
    ENCUADRES = "encuadres"    # faltan keyframes elegidos por escena
    RENDER = "render"          # falta renderizar el video
    PAQUETE = "paquete"        # falta armar el paquete de edicion (export)
    COMPLETO = "completo"      # todo listo


# Orden canonico del bucle -> permite preguntar "esta etapa ya paso?".
STAGE_ORDER: list[Stage] = [
    Stage.SIN_CLAVES, Stage.GUION, Stage.CASTING, Stage.ENCUADRES,
    Stage.RENDER, Stage.PAQUETE, Stage.COMPLETO,
]


@dataclass
class CastingState:
    needed: int          # personajes con design: (que requieren casting)
    chosen: int          # cuantos ya tienen cara elegida
    has_candidates: bool


@dataclass
class KeyframesState:
    total: int           # escenas
    chosen: int          # escenas con keyframe elegido
    has_candidates: bool


@dataclass
class RenderState:
    done: bool
    run_id: str | None


@dataclass
class ProjectState:
    stage: Stage
    scenes_total: int
    storyboard_signed: bool
    casting: CastingState
    keyframes: KeyframesState
    render: RenderState
    export_done: bool

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "scenes_total": self.scenes_total,
            "storyboard": {"signed": self.storyboard_signed},
            "casting": vars(self.casting),
            "keyframes": vars(self.keyframes),
            "render": {"done": self.render.done, "run_id": self.render.run_id},
            "export": {"done": self.export_done},
        }


def compute_stage(*, has_fal_key: bool, storyboard_signed: bool,
                  casting: CastingState, keyframes: KeyframesState,
                  render_done: bool, export_done: bool) -> Stage:
    """La maquina de estados, pura: el stage es el PRIMER paso incompleto.

    El orden codifica los guards -- no se llega a RENDER sin ENCUADRES, ni a
    PAQUETE sin RENDER. Sin escenas/personajes, esos pasos no aplican y se saltan.
    """
    if not has_fal_key:
        return Stage.SIN_CLAVES
    if not storyboard_signed:
        return Stage.GUION
    if casting.needed > 0 and casting.chosen < casting.needed:
        return Stage.CASTING
    if keyframes.total > 0 and keyframes.chosen < keyframes.total:
        return Stage.ENCUADRES
    if not render_done:
        return Stage.RENDER
    if not export_done:
        return Stage.PAQUETE
    return Stage.COMPLETO


def signing_advisories(spec: ProjectSpec, routing, providers: dict) -> list[dict]:
    """Avisos NO bloqueantes sobre incompletitudes al firmar el storyboard (D-055/D-057).

    No invalida (coherente con D-046, "advertir, no invalidar"): solo nombra lo que
    de otro modo el humano descubre recién en el render. Cada aviso es
    `{scene, kind, msg}`:
      - `no_shots`: la escena no define planos -> se sintetiza 1 implícito.
      - `unknown_class`: la `class_` no existe en el perfil -> cae a 'standard'.
      - `dialogue_no_voice` (D-057): hay `dialogue` pero ningún `voiceover` -> el TTS
        solo dobla `voiceover`, así que la línea se VE (caption) pero no se ESCUCHA.
      - `unroutable` (D-057): ningún provider del perfil cumple las capabilities de la
        escena (p.ej. `needs_audio` sin provider de audio) -> fallaría en el render.
      - `hero_thin_coverage` (D-062): una escena hero con <3 planos desperdicia el
        clímax (el oficio pide establecimiento/medio/detalle o reacción).
      - `vo_too_long` (D-062): la locución estimada excede el plano -> la voz se
        cortaría a mitad de palabra (el video manda la duración en el mux).
      - `repeated_framing` (D-062): dos planos consecutivos con el MISMO encuadre
        explícito (tamaño+ángulo) -> el corte "salta feo".
      (El antiguo `short_shot_billing` se retiró en D-068: el bloque del proveedor
      es COBERTURA para la edición, no desperdicio — el dato vive en el animatic.)

    `routing`/`providers` vienen del Config activo (perfil); la elegibilidad la decide
    `routing_gaps` (misma lógica pura que el guard temprano del runner)."""
    from .project import effective_shots
    from .strategies.dispatch import routing_gaps  # local: evita ciclo de imports
    routing_classes = set(routing.rules)
    out: list[dict] = []
    for s in spec.scenes:
        if not s.shots:
            out.append({"scene": s.id, "kind": "no_shots",
                        "msg": "no define planos; se usará 1 plano implícito."})
        if s.class_ and s.class_ not in routing_classes:
            out.append({"scene": s.id, "kind": "unknown_class",
                        "msg": f"la clase '{s.class_}' no existe en el perfil; se enruta como 'standard'."})
        if s.dialogue and not (s.voiceover or any(sh.voiceover for sh in s.shots)):
            out.append({"scene": s.id, "kind": "dialogue_no_voice",
                        "msg": "tiene diálogo pero ningún 'voiceover'; se verá como texto pero no se "
                               "escuchará (el TTS solo dobla 'voiceover')."})
        # D-062: gramática de cobertura y plata, por escena.
        shots = effective_shots(s)
        if s.class_ == "hero" and len(shots) < 3:
            out.append({"scene": s.id, "kind": "hero_thin_coverage",
                        "msg": f"es hero con {len(shots)} plano(s); el clímax merece cobertura "
                               "(establecimiento / medio / detalle o reacción)."})
        for i, sh in enumerate(shots, start=1):
            vo = sh.voiceover or ""
            if vo and len(vo.split()) / WORDS_PER_SECOND > sh.duration_s + 0.5:
                est = len(vo.split()) / WORDS_PER_SECOND
                out.append({"scene": s.id, "kind": "vo_too_long",
                            "msg": f"la voz del plano {i} dura ~{est:.1f}s y el plano {sh.duration_s:g}s; "
                                   "se cortaría a mitad de palabra (alarga el plano o acorta la línea)."})
        # D-068: el aviso short_shot_billing se RETIRA — empujaba planos largos y
        # ritmo lento. Las duraciones del autor son de EDICIÓN; el bloque del
        # proveedor es COBERTURA. El pagado-vs-usado vive como INFO en el animatic.
    # D-062: encuadre repetido en cortes consecutivos, a través de TODO el film.
    film = [(s.id, sh) for s in spec.scenes for sh in effective_shots(s)]
    for (_, prev), (sid, cur) in zip(film, film[1:]):
        same = (prev.camera.size == cur.camera.size and prev.camera.angle == cur.camera.angle)
        if same and not (prev.camera.is_default() and cur.camera.is_default()):
            out.append({"scene": sid, "kind": "repeated_framing",
                        "msg": f"corte entre dos planos con el mismo encuadre ({cur.camera.size}/"
                               f"{cur.camera.angle}); variá tamaño o ángulo para que el corte respire."})
    for gap in routing_gaps(spec, routing, providers):
        out.append({"scene": gap["scene"], "kind": "unroutable",
                    "msg": f"ninguna fuente del perfil puede generar esta escena (falta: "
                           f"{', '.join(gap['missing'])}); quita el requisito o cambia de perfil."})
    return out


# D-062: constantes de oficio/facturación (puras, parametrizables en los helpers).
WORDS_PER_SECOND = 2.5   # ritmo de locución conversacional estimado (es-LA)
BILLING_BLOCK_S = 5.0    # bloque mínimo que factura el proveedor de video (Kling)


def _block_paid(duration_s: float, block_s: float = BILLING_BLOCK_S) -> float:
    """Segundos FACTURADOS por un plano: bloques completos del proveedor. Pura."""
    import math
    return math.ceil(max(duration_s, 0.0001) / block_s) * block_s


def billing_summary(spec: ProjectSpec, block_s: float = BILLING_BLOCK_S) -> dict:
    """Segundos pagados vs usados de todo el film (D-062): la plata visible.

    `paid_s` = bloques del proveedor por plano; `used_s` = lo que queda en el corte."""
    from .project import effective_shots
    shots = [sh for s in spec.scenes for sh in effective_shots(s)]
    used = sum(sh.duration_s for sh in shots)
    paid = sum(_block_paid(sh.duration_s, block_s) for sh in shots)
    return {"paid_s": paid, "used_s": used, "wasted_s": round(paid - used, 2)}


def estimate_image_cost(n_scenes: int, n_per_scene: int, cost_per_image: float) -> float:
    """Costo estimado de generar `n_per_scene` candidatos para `n_scenes` escenas (T15/D-055)."""
    return round(max(0, n_scenes) * max(0, n_per_scene) * max(0.0, cost_per_image), 4)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def derive_state(project: Project, spec: ProjectSpec, *, has_fal_key: bool) -> ProjectState:
    """Lee los artefactos del proyecto y deriva su estado. Barato; no genera nada."""
    scene_ids = [s.id for s in spec.scenes]
    designed = [name for name, ch in spec.characters.items() if ch.design]

    casting_chosen = _load_yaml(project.dir / "casting.yaml")
    casting = CastingState(
        needed=len(designed),
        chosen=sum(1 for n in designed if n in casting_chosen),
        has_candidates=(project.dir / "cast_candidates.yaml").exists(),
    )

    selections = _load_yaml(project.selections_path)
    keyframes = KeyframesState(
        total=len(scene_ids),
        # Cuenta elegido solo si el archivo EXISTE (resuelto project-relative): un
        # proyecto importado con selections de otra máquina no debe figurar "listo"
        # cuando los frames no están en disco (D-044).
        chosen=sum(1 for sid in scene_ids
                   if sid in selections and _resolve_under(project.dir, selections[sid]).exists()),
        has_candidates=project.candidates_path.exists(),
    )

    storyboard_signed = (project.dir / "storyboard.signed").exists()

    run = project.latest_run()
    render = RenderState(done=run is not None, run_id=run.run_id if run is not None else None)
    export_done = (project.dir / "export").exists()

    stage = compute_stage(
        has_fal_key=has_fal_key, storyboard_signed=storyboard_signed,
        casting=casting, keyframes=keyframes,
        render_done=render.done, export_done=export_done,
    )
    return ProjectState(stage=stage, scenes_total=len(scene_ids),
                        storyboard_signed=storyboard_signed,
                        casting=casting, keyframes=keyframes, render=render,
                        export_done=export_done)
