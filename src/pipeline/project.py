"""Modelo de proyecto + caché content-addressed (SPEC §7).

Un proyecto soporta muchas iteraciones baratas: cada paso de cada escena se
llavea por el hash de sus inputs y se cachea a nivel proyecto, asi re-correr sin
cambios cuesta $0 y cambiar una escena solo regenera esa. Los runs son
materializaciones inmutables (un manifiesto + el render final).

`cache_key`, `Project` y `Run` son logica pura (sin I/O de red) -> core testeable.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .contracts import Scene, Shot


def cache_key(step: str, inputs: dict) -> str:
    """Hash determinista de (step, inputs). Independiente del orden del dict.

    El `step` actua de namespace: mismos inputs en pasos distintos -> keys
    distintas. Cambiar cualquier input cambia la key.
    """
    payload = json.dumps(inputs, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(f"{step}::{payload}".encode("utf-8")).hexdigest()
    return digest[:16]


class CharacterDesign(BaseModel):
    """Inputs para diseñar la cara canónica del personaje (casting, Sprint 4.6)."""

    prompt: str
    refs: list[Path] = Field(default_factory=list)  # p.ej. [persona, referencia LEGO]


class Character(BaseModel):
    """Personaje con imagen(es) de referencia para propagar identidad (Sprint 4)."""

    name: str
    refs: list[Path] = Field(default_factory=list)  # canónica (estática o elegida por casting)
    design: CharacterDesign | None = None  # inputs de diseño para `pipeline cast`


@dataclass
class ProjectSpec:
    """`project.yaml` parseado: la entrada unica que dispara el pipeline."""

    slug: str
    style: str
    format: str
    scenes: list[Scene] = field(default_factory=list)
    characters: dict[str, Character] = field(default_factory=dict)
    music: Path | None = None  # pista de música de fondo (opcional)
    voice_id: str | None = None  # voz por defecto del proyecto (ElevenLabs); override por escena
    title: str | None = None  # título legible (para el guion de export, D-029)
    brief: str | None = None  # brief del proyecto (para el guion de export, D-029)


def load_project_spec(path: Path) -> ProjectSpec:
    """Lee y valida un project.yaml -> ProjectSpec (escenas + banco de personajes)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if "scenes" not in data:
        raise ValueError(f"{path} debe tener 'scenes'.")
    scenes = [Scene(**s) for s in data["scenes"]]
    characters = {
        name: Character(
            name=name,
            refs=[Path(r) for r in (cspec.get("refs") or [])],
            design=(
                CharacterDesign(
                    prompt=cspec["design"]["prompt"],
                    refs=[Path(r) for r in (cspec["design"].get("refs") or [])],
                )
                if cspec.get("design")
                else None
            ),
        )
        for name, cspec in (data.get("characters") or {}).items()
    }
    return ProjectSpec(
        slug=data.get("project", path.parent.name),
        style=data.get("style", "lego"),
        format=str(data.get("format", "9:16")),
        scenes=scenes,
        characters=characters,
        music=Path(data["music"]) if data.get("music") else None,
        voice_id=data.get("voice_id"),
        title=data.get("title"),
        brief=data.get("brief"),
    )


def effective_shots(scene: Scene) -> list[Shot]:
    """Planos de la escena (D-028). Si no hay `shots:`, sintetiza **1 plano implícito**
    con los campos de la escena → el runner/studio iteran planos siempre (compat)."""
    if scene.shots:
        return scene.shots
    return [Shot(framing="", duration_s=scene.duration_s, seed=scene.seed,
                 voiceover=scene.voiceover, caption=scene.caption, keyframe=scene.keyframe)]


def character_refs(scene: Scene, characters: dict[str, Character]) -> list[Path]:
    """Reúne las referencias de los personajes de la escena (orden, sin duplicados)."""
    out: list[Path] = []
    for name in scene.characters:
        ch = characters.get(name)
        if not ch:
            continue
        for ref in ch.refs:
            if ref not in out:
                out.append(ref)
    return out


@dataclass
class Run:
    """Una materializacion inmutable del spec del proyecto."""

    run_id: str
    dir: Path

    @property
    def report_path(self) -> Path:
        return self.dir / "run_report.json"

    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.yaml"


class Project:
    """Agrupa el spec, el cache (compartido entre runs) y los runs de un proyecto."""

    def __init__(self, slug: str, root: Path = Path("projects")):
        self.slug = slug
        self.dir = Path(root) / slug

    @property
    def cache_dir(self) -> Path:
        return self.dir / "cache"

    @property
    def runs_dir(self) -> Path:
        return self.dir / "runs"

    @property
    def spec_path(self) -> Path:
        return self.dir / "project.yaml"

    @property
    def candidates_path(self) -> Path:
        return self.dir / "candidates.yaml"  # keyframes generados por escena (D-022)

    @property
    def selections_path(self) -> Path:
        return self.dir / "selections.yaml"  # elección humana por escena (D-022)

    # --- runs --------------------------------------------------------------

    def new_run(self) -> Run:
        """Crea una carpeta de run unica (no pisa iteraciones previas)."""
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        return Run(run_id=run_id, dir=run_dir)

    def latest_run(self) -> Run | None:
        """El run más reciente (el run_id lleva timestamp -> orden lexicográfico). None si no hay."""
        if not self.runs_dir.exists():
            return None
        dirs = sorted(d for d in self.runs_dir.iterdir() if d.is_dir())
        return Run(run_id=dirs[-1].name, dir=dirs[-1]) if dirs else None

    # --- cache content-addressed (nivel proyecto) --------------------------

    def _cache_path(self, category: str, key: str, ext: str) -> Path:
        return self.cache_dir / category / f"{key}{ext}"

    def cache_lookup(self, category: str, key: str, ext: str) -> Path | None:
        """Devuelve el path cacheado si existe (hit), o None (miss). No crea nada."""
        path = self._cache_path(category, key, ext)
        return path if path.exists() else None

    def cache_store(self, category: str, key: str, src: Path, ext: str) -> Path:
        """Guarda `src` en el cache bajo `key` y devuelve el path destino."""
        dest = self._cache_path(category, key, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(src).read_bytes())
        return dest

    # --- sidecar de metadatos (preserva procedencia en cache hits) ---------

    def _sidecar_path(self, category: str, key: str) -> Path:
        return self.cache_dir / category / f"{key}.meta.json"

    def sidecar_store(self, category: str, key: str, data: dict) -> Path:
        """Guarda metadatos junto al artefacto (p.ej. qué provider lo generó)."""
        path = self._sidecar_path(category, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def sidecar_lookup(self, category: str, key: str) -> dict | None:
        path = self._sidecar_path(category, key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
