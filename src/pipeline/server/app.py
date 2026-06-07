"""FastAPI del Studio local (D-031, Fase 1).

Cáscara fina sobre el motor: cada endpoint llama a `studio`/`runner`/`export`.
Las generaciones se lanzan como jobs (progreso en vivo por SSE); las selecciones
(`pick`/`pick-cast`) y los ajustes son síncronos. Local, sin auth.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..settings import get_settings
from .jobs import JobManager

_KEYS = {"fal_key": "FAL_KEY", "anthropic_api_key": "ANTHROPIC_API_KEY",
         "elevenlabs_api_key": "ELEVENLABS_API_KEY"}

# Campos de escena editables desde el storyboard (D-033). El resto (seed, class,
# requirements, dialogue, voice_id, keyframe) se preserva del spec en disco.
_EDITABLE_SCENE = {"prompt", "beat", "duration_s", "caption", "voiceover", "characters", "shots"}


def _available_styles(config_dir: Path) -> list[str]:
    """Estilos disponibles = `config/styles/*.yaml` (para el selector del import, #10)."""
    styles_dir = config_dir / "styles"
    return sorted(p.stem for p in styles_dir.glob("*.yaml")) if styles_dir.exists() else []


def _unique_slug(base: str, projects_dir: Path) -> str:
    """Slug de proyecto único y filesystem-safe (no pisa una carpeta existente)."""
    from ..naming import _slugify

    base = _slugify(base) or "proyecto"
    slug, i = base, 2
    while (projects_dir / slug).exists():
        slug, i = f"{base}_{i}", i + 1
    return slug


def create_app(projects_dir: Path = Path("projects"),
               config_dir: Path = Path("config")) -> FastAPI:
    projects_dir = Path(projects_dir)
    config_dir = Path(config_dir)
    app = FastAPI(title="Video Studio (local)")
    jobs = JobManager()

    # --- helpers ----------------------------------------------------------
    def load(slug: str):
        from ..config import load_config
        from ..project import Project, load_project_spec
        from ..studio import apply_casting, load_casting

        project = Project(slug, root=projects_dir)
        if not project.spec_path.exists():
            raise HTTPException(404, f"Proyecto '{slug}' no existe.")
        spec = load_project_spec(project.spec_path)
        cfg = load_config(config_dir, spec.style)
        apply_casting(spec.characters, load_casting(project))
        return project, spec, cfg

    def file_url(p) -> str | None:
        try:
            rel = Path(p).resolve().relative_to(projects_dir.resolve())
            return "/files/" + rel.as_posix()
        except Exception:
            return None

    # --- proyectos --------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/styles")
    def list_styles():
        return _available_styles(config_dir)

    @app.get("/api/projects")
    def list_projects():
        from ..project import load_project_spec

        out = []
        if projects_dir.exists():
            for d in sorted(projects_dir.iterdir()):
                spec_path = d / "project.yaml"
                if spec_path.exists():
                    try:
                        spec = load_project_spec(spec_path)
                        out.append({"slug": d.name, "title": spec.title or d.name,
                                    "style": spec.style, "scenes": len(spec.scenes)})
                    except Exception:
                        out.append({"slug": d.name, "title": d.name, "style": "?", "scenes": 0})
        return out

    # --- administrar proyectos: crear / borrar (#3, Fase 2.5) -------------
    @app.post("/api/projects")
    def create_project(body: dict):
        """Crea un proyecto **en blanco** (además del import): título + estilo,
        sin escenas. Devuelve el slug (único, derivado del título si no se pasa)."""
        from ..project import Project, ProjectSpec, write_spec

        title = (body.get("title") or "").strip() or "Nuevo proyecto"
        style = (body.get("style") or "lego").strip()
        if style not in _available_styles(config_dir):
            raise HTTPException(422, f"Estilo desconocido: '{style}'.")
        slug = _unique_slug((body.get("slug") or "").strip() or title, projects_dir)
        project = Project(slug, root=projects_dir)
        write_spec(
            ProjectSpec(slug=slug, style=style, format="9:16", title=title, scenes=[]),
            project.spec_path,
        )
        return {"slug": slug, "title": title, "style": style}

    @app.delete("/api/projects/{slug}")
    def delete_project(slug: str):
        """Borra el proyecto **entero** (spec + cache + runs + export). Destructivo;
        la UI confirma antes. Devuelve el slug borrado."""
        import shutil

        from ..project import Project

        project = Project(slug, root=projects_dir)
        if not project.spec_path.exists():
            raise HTTPException(404, f"Proyecto '{slug}' no existe.")
        shutil.rmtree(project.dir)
        return {"deleted": slug}

    # --- entrada desde la app: importar -> storyboard (D-033, Fase 2) -----
    @app.post("/api/projects/import")
    async def import_project(body: dict):
        """Texto libre -> borrador de proyecto (la IA propone). Job/SSE: devuelve el
        slug creado. La UI lee el .md/.txt client-side y manda el texto acá."""
        import logging

        from .. import author
        from ..naming import semantic_slug
        from ..project import Project, write_spec

        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(422, "Pegá o subí un texto para importar.")
        desired = (body.get("slug") or "").strip()
        style = (body.get("style") or "").strip()
        if style and style not in _available_styles(config_dir):
            raise HTTPException(422, f"Estilo desconocido: '{style}'.")
        log = logging.getLogger("pipeline")

        async def coro():
            log.info("Descomponiendo el texto en un borrador (Claude)...")
            draft = await asyncio.to_thread(author.draft_project, text)
            if style:  # estilo elegido en la UI gana sobre el default del borrador (#10)
                draft.style = style
            slug = _unique_slug(desired or semantic_slug(draft.title), projects_dir)
            project = Project(slug, root=projects_dir)
            write_spec(draft.to_spec(slug), project.spec_path)
            log.info("Proyecto '%s' creado: %d escenas.", slug, len(draft.scenes))
            return {"slug": slug, "title": draft.title, "scenes": len(draft.scenes)}

        return jobs.spawn("import", desired or "(nuevo)", coro()).to_dict()

    @app.put("/api/projects/{slug}")
    def update_project(slug: str, body: dict):
        """Guarda el storyboard editado (D-033). Preserva los campos no editables
        de cada escena; valida con Pydantic (422 si algo no cierra) y aplica el
        guard de selecciones (D-022) si se renombraron/eliminaron escenas."""
        from ..contracts import Scene
        from ..project import Project, load_project_spec, write_spec
        from ..studio import prune_selections

        project = Project(slug, root=projects_dir)
        if not project.spec_path.exists():
            raise HTTPException(404, f"Proyecto '{slug}' no existe.")
        spec = load_project_spec(project.spec_path)
        existing = {s.id: s for s in spec.scenes}

        raw_scenes = body.get("scenes")
        if not raw_scenes:
            raise HTTPException(422, "El storyboard necesita al menos una escena.")
        try:
            new_scenes = []
            for i, raw in enumerate(raw_scenes):
                sid = (raw.get("id") or "").strip() or f"s{i + 1}"
                base = existing.get(sid)
                data = base.model_dump(by_alias=True) if base else {}
                data.update({k: raw[k] for k in _EDITABLE_SCENE if k in raw})
                data["id"] = sid
                scene = Scene(**data)
                if scene.shots:  # el total de la escena = suma de sus planos
                    scene.duration_s = sum(sh.duration_s for sh in scene.shots)
                new_scenes.append(scene)
        except Exception as exc:  # noqa: BLE001 — validación -> 422 legible
            raise HTTPException(422, f"Storyboard inválido: {exc}")

        ids = [s.id for s in new_scenes]
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "Hay ids de escena repetidos.")

        spec.scenes = new_scenes
        if "title" in body:
            spec.title = body["title"]
        if "brief" in body:
            spec.brief = body["brief"]
        write_spec(spec, project.spec_path)
        dropped = prune_selections(project, ids)
        # "Firmar el plan" (D-021/#5): un marcador en disco; editar sin firmar lo
        # limpia (el plan cambió → hay que volver a firmar). Estado derivado (D-032).
        signed_marker = project.dir / "storyboard.signed"
        if body.get("sign"):
            signed_marker.write_text("", encoding="utf-8")
        else:
            signed_marker.unlink(missing_ok=True)
        return {"saved": str(project.spec_path), "scenes": len(ids),
                "dropped_selections": dropped, "signed": bool(body.get("sign"))}

    @app.get("/api/projects/{slug}")
    def project_detail(slug: str):
        from ..project import effective_shots

        _project, spec, _cfg = load(slug)
        scenes = [{
            "id": s.id, "beat": s.beat, "class": s.class_, "prompt": s.prompt,
            "characters": s.characters,
            "shots": [{"framing": sh.framing, "duration_s": sh.duration_s,
                       "voiceover": sh.voiceover, "caption": sh.caption}
                      for sh in effective_shots(s)],
        } for s in spec.scenes]
        characters = [{
            "name": name,
            "design": ch.design.prompt if ch.design else None,
            "refs": [str(r) for r in (ch.refs or [])],
        } for name, ch in spec.characters.items()]
        return {"slug": slug, "title": spec.title or slug, "brief": spec.brief,
                "style": spec.style, "format": spec.format,
                "characters": characters, "scenes": scenes}

    @app.get("/api/projects/{slug}/candidates")
    def candidates(slug: str):
        project, _spec, _cfg = load(slug)

        def read(path: Path) -> dict:
            if not path.exists():
                return {}
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return {k: [file_url(p) for p in v] for k, v in data.items()}

        return {"keyframes": read(project.candidates_path),
                "cast": read(project.dir / "cast_candidates.yaml")}

    @app.get("/api/projects/{slug}/status")
    def project_status(slug: str):
        """Estado derivado del proyecto para la pantalla de Inicio: qué hay hecho y
        cuál es el siguiente paso. Lectura barata de archivos en disco (sin generar)."""
        from ..studio import load_casting

        project, spec, _cfg = load(slug)
        s = get_settings()
        keys = {attr: bool(getattr(s, attr)) for attr in _KEYS}

        scene_ids = [sc.id for sc in spec.scenes]
        designed = [name for name, ch in spec.characters.items() if ch.design]
        casting = load_casting(project)
        cast_chosen = [n for n in designed if n in casting]

        selections = {}
        if project.selections_path.exists():
            selections = yaml.safe_load(project.selections_path.read_text(encoding="utf-8")) or {}
        chosen_scenes = [sid for sid in scene_ids if sid in selections]

        run = project.latest_run()
        final_url = None
        if run is not None:
            final = next(iter(run.dir.glob("final_*.mp4")), None)
            final_url = file_url(final) if final else None
        export_dir = project.dir / "export"

        return {
            "keys": keys,
            "scenes_total": len(scene_ids),
            "storyboard": {"signed": (project.dir / "storyboard.signed").exists()},
            "casting": {"needed": len(designed), "chosen": len(cast_chosen),
                        "has_candidates": (project.dir / "cast_candidates.yaml").exists()},
            "keyframes": {"total": len(scene_ids), "chosen": len(chosen_scenes),
                          "has_candidates": project.candidates_path.exists()},
            "render": {"done": run is not None,
                       "run_id": run.run_id if run is not None else None,
                       "final_url": final_url},
            "export": {"done": export_dir.exists()},
        }

    # --- jobs de generación ----------------------------------------------
    @app.post("/api/projects/{slug}/keyframes")
    async def gen_keyframes(slug: str, n: int = 4):
        from .. import studio

        project, spec, cfg = load(slug)

        async def coro():
            sheet = await studio.gen_keyframes(project, spec, cfg, n, open_sheet=False)
            return {"sheet": str(sheet)}

        return jobs.spawn("keyframes", slug, coro()).to_dict()

    @app.post("/api/projects/{slug}/cast")
    async def gen_cast(slug: str, n: int = 4):
        from .. import studio

        project, spec, cfg = load(slug)

        async def coro():
            sheet = await studio.cast(project, spec, cfg, n, open_sheet=False)
            return {"sheet": str(sheet)}

        return jobs.spawn("cast", slug, coro()).to_dict()

    @app.post("/api/projects/{slug}/render")
    async def render(slug: str):
        from .. import studio

        project, spec, cfg = load(slug)

        async def coro():
            run, final, totals = await studio.render(project, spec, cfg)
            return {"run_id": run.run_id, "final": str(final), **totals}

        return jobs.spawn("render", slug, coro()).to_dict()

    @app.post("/api/projects/{slug}/export")
    async def export(slug: str):
        from ..export import export_bundle

        project, spec, _cfg = load(slug)

        async def coro():
            out = await asyncio.to_thread(export_bundle, project, spec)
            return {"export": str(out)}

        return jobs.spawn("export", slug, coro()).to_dict()

    # --- selección (síncrona) --------------------------------------------
    @app.post("/api/projects/{slug}/pick")
    def pick(slug: str, body: dict):
        from ..studio import record_picks

        project, _spec, _cfg = load(slug)
        path = record_picks(project, {k: int(v) for k, v in (body.get("picks") or {}).items()})
        return {"saved": str(path)}

    @app.post("/api/projects/{slug}/pick-cast")
    def pick_cast(slug: str, body: dict):
        from ..studio import record_cast_picks

        project, _spec, _cfg = load(slug)
        path = record_cast_picks(project, {k: int(v) for k, v in (body.get("picks") or {}).items()})
        return {"saved": str(path)}

    # --- jobs: estado + stream -------------------------------------------
    @app.get("/api/jobs")
    def list_jobs():
        return [j.to_dict() for j in jobs.list()]

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job desconocido.")
        return {**job.to_dict(), "logs": job.logs}

    @app.get("/api/jobs/{job_id}/stream")
    async def job_stream(job_id: str):
        if jobs.get(job_id) is None:
            raise HTTPException(404, "Job desconocido.")

        async def gen():
            async for line in jobs.stream(job_id):
                yield f"data: {line}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    # --- ajustes (API keys) ----------------------------------------------
    @app.get("/api/settings")
    def get_settings_status():
        s = get_settings()
        return {attr: bool(getattr(s, attr)) for attr in _KEYS}

    @app.put("/api/settings")
    def put_settings(body: dict):
        env = Path(".env")
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        current = {ln.split("=", 1)[0]: ln for ln in lines if "=" in ln and not ln.startswith("#")}
        for attr, env_name in _KEYS.items():
            if attr in body and body[attr] is not None:
                current[env_name] = f"{env_name}={body[attr]}"
        env.write_text("\n".join(current.values()) + "\n", encoding="utf-8")
        get_settings.cache_clear()  # que el próximo get_settings lea las nuevas keys
        return get_settings_status()

    # --- estáticos (imágenes de candidatos + UI build) -------------------
    if projects_dir.exists():
        app.mount("/files", StaticFiles(directory=projects_dir), name="files")
    ui_dist = Path(__file__).resolve().parents[3] / "app" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    return app


app = create_app(
    projects_dir=Path(os.environ.get("STUDIO_PROJECTS_DIR", "projects")),
    config_dir=Path(os.environ.get("STUDIO_CONFIG_DIR", "config")),
)
