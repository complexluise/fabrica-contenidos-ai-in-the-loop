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

from .project import Project, ProjectSpec


class Stage(str, Enum):
    """El primer paso pendiente del bucle. COMPLETO = no queda nada por hacer."""

    SIN_CLAVES = "sin_claves"  # falta FAL_KEY (prerequisito de todo)
    CASTING = "casting"        # hay personajes con design: sin cara elegida
    ENCUADRES = "encuadres"    # faltan keyframes elegidos por escena
    RENDER = "render"          # falta renderizar el video
    PAQUETE = "paquete"        # falta armar el paquete de edicion (export)
    COMPLETO = "completo"      # todo listo


# Orden canonico del bucle -> permite preguntar "esta etapa ya paso?".
STAGE_ORDER: list[Stage] = [
    Stage.SIN_CLAVES, Stage.CASTING, Stage.ENCUADRES,
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
    casting: CastingState
    keyframes: KeyframesState
    render: RenderState
    export_done: bool

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "scenes_total": self.scenes_total,
            "casting": vars(self.casting),
            "keyframes": vars(self.keyframes),
            "render": {"done": self.render.done, "run_id": self.render.run_id},
            "export": {"done": self.export_done},
        }


def compute_stage(*, has_fal_key: bool, casting: CastingState, keyframes: KeyframesState,
                  render_done: bool, export_done: bool) -> Stage:
    """La maquina de estados, pura: el stage es el PRIMER paso incompleto.

    El orden codifica los guards -- no se llega a RENDER sin ENCUADRES, ni a
    PAQUETE sin RENDER. Sin escenas/personajes, esos pasos no aplican y se saltan.
    """
    if not has_fal_key:
        return Stage.SIN_CLAVES
    if casting.needed > 0 and casting.chosen < casting.needed:
        return Stage.CASTING
    if keyframes.total > 0 and keyframes.chosen < keyframes.total:
        return Stage.ENCUADRES
    if not render_done:
        return Stage.RENDER
    if not export_done:
        return Stage.PAQUETE
    return Stage.COMPLETO


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
        chosen=sum(1 for sid in scene_ids if sid in selections),
        has_candidates=project.candidates_path.exists(),
    )

    run = project.latest_run()
    render = RenderState(done=run is not None, run_id=run.run_id if run is not None else None)
    export_done = (project.dir / "export").exists()

    stage = compute_stage(
        has_fal_key=has_fal_key, casting=casting, keyframes=keyframes,
        render_done=render.done, export_done=export_done,
    )
    return ProjectState(stage=stage, scenes_total=len(scene_ids), casting=casting,
                        keyframes=keyframes, render=render, export_done=export_done)
