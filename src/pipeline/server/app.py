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
