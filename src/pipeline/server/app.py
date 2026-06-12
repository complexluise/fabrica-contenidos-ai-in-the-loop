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
from pydantic import BaseModel

from ..config import DEFAULT_PROFILE
from ..settings import get_settings
from .jobs import JobManager


# --- Bodies tipados (D-077). `update_project` queda como dict a proposito:
# su semantica es de MERGE PARCIAL campo a campo (D-033/D-047) y un modelo
# con defaults no distingue "no vino" de "vino vacio".
class CreateProjectBody(BaseModel):
    title: str = ""
    style: str = "lego"
    slug: str = ""


class ImportBody(BaseModel):
    text: str = ""
    slug: str = ""
    style: str = ""


class CompileBody(BaseModel):
    scene_id: str = ""
    force: bool = False


class ShotsBody(BaseModel):
    force: bool = False
    backend: str | None = None


class UploadBody(BaseModel):
    data: str = ""
    filename: str = ""


class MusicGenBody(BaseModel):
    prompt: str = ""
    duration_s: float = 30.0


class PicksBody(BaseModel):
    picks: dict[str, int] = {}


class RenderBody(BaseModel):
    profile: str = DEFAULT_PROFILE  # D-076: gastar mas es opt-in explicito
    concurrency: int = 1


class PosePickBody(BaseModel):
    path: str = ""


def merge_env_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    """Mezcla claves en un .env PRESERVANDO comentarios y claves ajenas (D-078).

    Antes el guardado desde la UI reescribía el archivo solo con las líneas
    `k=v` — los comentarios del humano se perdían en cada guardado. Pura."""
    out: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        stripped = ln.strip()
        key = None
        if "=" in ln and not stripped.startswith("#"):
            key = ln.split("=", 1)[0].strip()
        if key is not None and key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(ln)
    out.extend(f"{k}={v}" for k, v in updates.items() if k not in seen)
    return out

_KEYS = {"fal_key": "FAL_KEY", "anthropic_api_key": "ANTHROPIC_API_KEY",
         "elevenlabs_api_key": "ELEVENLABS_API_KEY", "google_api_key": "GOOGLE_API_KEY"}

# Campos de escena editables desde el storyboard (D-033). El resto (seed, class,
# requirements, dialogue, voice_id, keyframe) se preserva del spec en disco.
# `shots` se mergea por indice (no se reemplaza) para que un editor parcial no
# borre los campos del artefacto (D-047) que no manda.
_EDITABLE_SCENE = {"prompt", "beat", "duration_s", "caption", "voiceover", "characters",
                   "dialogue", "ambience", "visual_intensity"}


def _available_styles(config_dir: Path) -> list[str]:
    """Estilos disponibles = `config/styles/*.yaml` (para el selector del import, #10)."""
    styles_dir = config_dir / "styles"
    return sorted(p.stem for p in styles_dir.glob("*.yaml")) if styles_dir.exists() else []


def _unique_slug(base: str, projects_dir: Path) -> str:
    """Slug de proyecto único y filesystem-safe (no pisa una carpeta existente)."""
    from ..naming import slugify

    base = slugify(base) or "proyecto"
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
    def safe_project(slug: str):
        """Resuelve el proyecto verificando que quede DENTRO de projects/ (D-077).

        Sin esto, un slug con separadores (`..%5C..` en Windows) escapaba del
        arbol — y `DELETE` hace rmtree. Una linea de guard, cero framework."""
        from ..project import Project

        project = Project(slug, root=projects_dir)
        if project.dir.parent != projects_dir.resolve():
            raise HTTPException(422, f"Slug invalido: '{slug}'.")
        return project

    def load(slug: str, profile: str = DEFAULT_PROFILE):
        from ..config import load_config
        from ..project import load_project_spec
        from ..studio import apply_casting, load_casting

        project = safe_project(slug)
        if not project.spec_path.exists():
            raise HTTPException(404, f"Proyecto '{slug}' no existe.")
        spec = load_project_spec(project.spec_path)
        # D-053: backend del storyboard persiste en project.yaml
        cfg = load_config(config_dir, spec.style, profile=profile,
                          backend=spec.storyboard_backend)
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

    @app.get("/api/profiles")
    def list_profiles():
        """Perfiles de renderizado disponibles leidos de routing.yaml."""
        raw = yaml.safe_load((config_dir / "routing.yaml").read_text(encoding="utf-8")) or {}
        profiles = raw.get("profiles", {})
        out = []
        for key, rules in profiles.items():
            meta = rules.get("_meta", {})
            # Inferir proveedor principal del perfil hero para mostrarlo
            hero_providers = (rules.get("hero") or {}).get("providers", [])
            out.append({
                "key":   key,
                "label": meta.get("label", key),
                "desc":  meta.get("desc", ""),
                "badge": meta.get("badge", key),
                "color": meta.get("color", "gray"),
                "providers": hero_providers,
            })
        return out

    @app.get("/api/storyboard-backends")
    def list_storyboard_backends():
        """Backends del storyboard (imagen + LLM) disponibles — D-053."""
        raw = yaml.safe_load((config_dir / "routing.yaml").read_text(encoding="utf-8")) or {}
        backends = raw.get("storyboard_backends", {})
        out = []
        for key, entry in backends.items():
            meta = entry.get("_meta", {})
            out.append({
                "key":   key,
                "label": meta.get("label", key),
                "desc":  meta.get("desc", ""),
                "badge": meta.get("badge", key),
                "color": meta.get("color", "gray"),
                "est_cost_per_image_usd": entry.get("est_cost_per_image_usd", 0.003),
            })
        return out

    @app.get("/api/voice-backends")
    def list_voice_backends():
        """Backends de voz/TTS disponibles (kokoro/elevenlabs) — D-058."""
        raw = yaml.safe_load((config_dir / "routing.yaml").read_text(encoding="utf-8")) or {}
        backends = raw.get("voice_backends", {})
        out = []
        for key, entry in backends.items():
            meta = entry.get("_meta", {})
            out.append({
                "key":   key,
                "label": meta.get("label", key),
                "desc":  meta.get("desc", ""),
                "badge": meta.get("badge", key),
                "color": meta.get("color", "gray"),
                "cost_per_char": entry.get("cost_per_char", 0.0),
            })
        return out

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
    def create_project(body: CreateProjectBody):
        """Crea un proyecto **en blanco** (además del import): título + estilo,
        sin escenas. Devuelve el slug (único, derivado del título si no se pasa)."""
        from ..project import ProjectSpec, write_spec

        title = body.title.strip() or "Nuevo proyecto"
        style = (body.style or "lego").strip()
        if style not in _available_styles(config_dir):
            raise HTTPException(422, f"Estilo desconocido: '{style}'.")
        slug = _unique_slug(body.slug.strip() or title, projects_dir)
        project = safe_project(slug)
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

        project = safe_project(slug)  # D-077: rmtree JAMAS fuera de projects/
        if not project.spec_path.exists():
            raise HTTPException(404, f"Proyecto '{slug}' no existe.")
        shutil.rmtree(project.dir)
        return {"deleted": slug}

    # --- entrada desde la app: importar -> storyboard (D-033, Fase 2) -----
    @app.post("/api/projects/import")
    async def import_project(body: ImportBody):
        """Texto libre -> borrador de proyecto (la IA propone). Job/SSE: devuelve el
        slug creado. La UI lee el .md/.txt client-side y manda el texto acá."""
        import logging

        from .. import author
        from ..naming import semantic_slug
        from ..project import write_spec

        text = body.text.strip()
        if not text:
            raise HTTPException(422, "Pegá o subí un texto para importar.")
        desired = body.slug.strip()
        style = body.style.strip()
        if style and style not in _available_styles(config_dir):
            raise HTTPException(422, f"Estilo desconocido: '{style}'.")
        log = logging.getLogger("pipeline")

        async def coro():
            log.info("Descomponiendo el texto en un borrador (Claude)...")
            draft = await asyncio.to_thread(author.draft_project, text)
            if style:  # estilo elegido en la UI gana sobre el default del borrador (#10)
                draft.style = style
            slug = _unique_slug(desired or semantic_slug(draft.title), projects_dir)
            project = safe_project(slug)
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
        from ..project import load_project_spec, write_spec
        from ..studio import prune_selections

        project = safe_project(slug)
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
                # D-047: `shots` se MERGEA por indice (no se reemplaza): las claves que
                # el cliente manda pisan al plano base; las que no manda se conservan.
                # Asi un editor parcial (Picker manda framing/audio) no borra camera/visual.
                if isinstance(raw.get("shots"), list):
                    base_shots = data.get("shots") or []
                    merged = []
                    for j, rsh in enumerate(raw["shots"]):
                        bsh = dict(base_shots[j]) if j < len(base_shots) else {}
                        bsh.update({k: v for k, v in (rsh or {}).items()})
                        merged.append(bsh)
                    data["shots"] = merged
                data["id"] = sid
                scene = Scene(**data)
                if scene.shots:  # el total de la escena = suma de sus planos
                    scene.duration_s = sum(sh.duration_s for sh in scene.shots)
                # D-046: si el humano edito el prompt a mano (difiere del base), es
                # un override -> marcar manual para que no se recompile solo. El
                # round-trip de un prompt sin cambios no toca el flag.
                if "prompt" in raw:
                    prev = (base.prompt if base else "") or ""
                    if (raw.get("prompt") or "") != prev:
                        scene.prompt_manual = True
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
        # D-053: backend del storyboard persiste en project.yaml
        if "storyboard_backend" in body and body["storyboard_backend"]:
            spec.storyboard_backend = body["storyboard_backend"]
        # D-058: backend de voz persiste en project.yaml
        if "voice_backend" in body and body["voice_backend"]:
            spec.voice_backend = body["voice_backend"]
        write_spec(spec, project.spec_path)
        dropped = prune_selections(project, ids)
        # "Firmar el plan" (D-021/#5): un marcador en disco; editar sin firmar lo
        # limpia (el plan cambió → hay que volver a firmar). Estado derivado (D-032).
        signed_marker = project.dir / "storyboard.signed"
        if body.get("sign"):
            signed_marker.write_text("", encoding="utf-8")
        else:
            signed_marker.unlink(missing_ok=True)
        # T7/T13/D-055: avisos no bloqueantes (clase fuera del perfil, escena sin
        # planos) al momento de firmar — "advertir, no invalidar" (D-046).
        advisories = []
        try:
            from ..config import load_config
            from ..state import signing_advisories
            cfg = load_config(config_dir, spec.style)
            advisories = signing_advisories(spec, cfg.routing, cfg.providers)
        except Exception:
            advisories = []
        return {"saved": str(project.spec_path), "scenes": len(ids),
                "dropped_selections": dropped, "signed": bool(body.get("sign")),
                "advisories": advisories}

    @app.get("/api/projects/{slug}")
    def project_detail(slug: str):
        from ..project import effective_shots
        from ..prompt_compile import compose_character_prompt

        _project, spec, _cfg = load(slug)
        scenes = [{
            "id": s.id, "beat": s.beat, "class": s.class_, "prompt": s.prompt,
            "prompt_manual": s.prompt_manual, "prompt_stale": s.prompt_stale,  # D-046
            "dialogue": s.dialogue, "ambience": s.ambience,
            "visual_intensity": s.visual_intensity,  # D-047
            "characters": s.characters,
            "shots": [{
                "intention": sh.intention, "action": sh.action,  # D-047
                "framing": sh.framing, "duration_s": sh.duration_s,
                "camera": sh.camera.model_dump(), "visual": sh.visual.model_dump(),  # D-047
                "transition": sh.transition,
                "voiceover": sh.voiceover, "caption": sh.caption, "sfx": sh.sfx,
            } for sh in effective_shots(s)],
        } for s in spec.scenes]
        characters = [{
            "name": name,
            "design": compose_character_prompt(ch.design) if ch.design else None,  # D-049/B2
            "refs": [str(r) for r in (ch.refs or [])],
        } for name, ch in spec.characters.items()]
        music_url = file_url(spec.music) if spec.music and Path(spec.music).exists() else None
        return {"slug": slug, "title": spec.title or slug, "brief": spec.brief,
                "style": spec.style, "format": spec.format, "music": music_url,
                "storyboard_backend": spec.storyboard_backend,  # D-053
                "voice_backend": spec.voice_backend,            # D-058
                "characters": characters, "scenes": scenes}

    @app.post("/api/projects/{slug}/prompts/compile")
    async def compile_prompts(slug: str, body: CompileBody | None = None):
        """Compila el prompt visual desde la narrativa (D-046). Sincrono (Haiku via
        to_thread). Body: { scene_id?, force? }. Con scene_id compila ESA escena
        (override explicito del humano); sin el, compila las desactualizadas
        (force incluye las en-sintonia y las manual)."""
        from ..project import write_spec
        from ..prompt_compile import sync_scene_prompt

        project, spec, _cfg = load(slug)
        body = body or CompileBody()
        scene_id = body.scene_id.strip() or None
        force = body.force
        targets = [s for s in spec.scenes if (scene_id is None or s.id == scene_id)]
        if scene_id and not targets:
            raise HTTPException(404, f"Escena '{scene_id}' no encontrada.")
        todo = [s for s in targets if (scene_id is not None or force or s.prompt_stale)]

        def work():
            from ..config import narrative_model
            for s in todo:
                sync_scene_prompt(s, spec.characters, model=narrative_model(_cfg.storyboard))
            if todo:
                write_spec(spec, project.spec_path)

        await asyncio.to_thread(work)
        return {"compiled": [{"id": s.id, "prompt": s.prompt,
                              "prompt_manual": s.prompt_manual,
                              "prompt_stale": s.prompt_stale} for s in todo]}

    @app.post("/api/projects/{slug}/shots/{scene_id}")
    async def gen_shot_previews(slug: str, scene_id: str, body: ShotsBody | None = None):
        """D-048/A4: genera (encadenados) los keyframes de los planos 2+ de la escena
        desde el ancla elegida, para previsualizar coherencia. Job/SSE."""
        from .. import studio

        project, spec, cfg = load(slug)
        if not any(s.id == scene_id for s in spec.scenes):
            raise HTTPException(404, f"Escena '{scene_id}' no encontrada.")
        body = body or ShotsBody()
        force = body.force
        backend = body.backend  # D-051: fal | google (toggle de Elegir)

        async def coro():
            paths = await studio.preview_shot_keyframes(project, spec, cfg, scene_id,
                                                        force=force, backend=backend)
            return {"scene": scene_id, "shots": len(paths)}

        return jobs.spawn("shots", f"{slug}/{scene_id}", coro()).to_dict()

    @app.get("/api/projects/{slug}/candidates")
    def candidates(slug: str):
        project, _spec, _cfg = load(slug)

        from ..project import read_yaml
        from ..studio import is_upload

        def read(path: Path) -> dict:
            return {k: [file_url(p) for p in v] for k, v in read_yaml(path).items()}

        def sources(path: Path) -> dict:
            """Origen de cada candidato: "upload" (humano) | "ia" (T11/D-055)."""
            return {k: ["upload" if is_upload(p) else "ia" for p in v]
                    for k, v in read_yaml(path).items()}

        return {"keyframes": read(project.candidates_path),
                "keyframe_sources": sources(project.candidates_path),  # T11
                "cast": read(project.dir / "cast_candidates.yaml"),
                "shot_previews": read(project.dir / "shot_previews.yaml"),  # D-048/A4
                "selections": read_yaml(project.selections_path),
                "cast_selections": read_yaml(project.dir / "casting.yaml")}

    @app.get("/api/projects/{slug}/status")
    async def project_status(slug: str):
        """Estado derivado del proyecto (D-032): el `stage` del bucle + el detalle
        por paso. La verdad se calcula en `state.derive_state`; aca solo decoramos
        con lo que es del server (claves de settings, URL del video final)."""
        from ..state import derive_state, signing_advisories
        from ..studio import verify_casting, verify_selections

        project, spec, _cfg = load(slug)
        s = get_settings()
        out = derive_state(project, spec, has_fal_key=bool(s.fal_key)).to_dict()
        out["keys"] = {attr: bool(getattr(s, attr)) for attr in _KEYS}
        # D-055: reconciliacion disco<->estado + avisos no bloqueantes + costo unitario.
        out["integrity"] = {"selections": verify_selections(project),  # T5/T14
                            "casting": verify_casting(project)}          # T10
        out["advisories"] = signing_advisories(spec, _cfg.routing, _cfg.providers)  # T7/T13/D-057
        out["est_cost_per_image_usd"] = _cfg.storyboard.est_cost_per_image_usd  # T15
        # D-061: avance del animatic (solo lectura, cero costo) para la espina/página.
        try:
            from ..studio import animatic_strip
            strip = await animatic_strip(project, spec, _cfg)
            missing = sum((0 if e["start"] else 1) + (0 if e["destino"] else 1) for e in strip)
            out["animatic"] = {
                "total": len(strip), "ready": sum(1 for e in strip if e["ready"]),
                "missing_poses": missing,
                "est_missing_cost_usd": round(missing * _cfg.storyboard.est_cost_per_image_usd, 4)}
        except Exception:
            out["animatic"] = None

        # D-078: master (film stock) > final; un run fallido no tiene URL.
        run = project.latest_run()
        final = run.final_render() if run is not None else None
        out["render"]["final_url"] = file_url(final) if final else None
        return out

    # --- jobs de generación ----------------------------------------------
    @app.post("/api/projects/{slug}/keyframes")
    async def gen_keyframes(slug: str, n: int = 4, concurrency: int = 5,
                            backend: str | None = None):
        from .. import studio

        project, spec, cfg = load(slug)

        async def coro():
            sheet = await studio.gen_keyframes(project, spec, cfg, n, open_sheet=False,
                                               concurrency=concurrency, backend=backend)
            return {"sheet": str(sheet)}

        return jobs.spawn("keyframes", slug, coro()).to_dict()

    @app.post("/api/projects/{slug}/keyframes/{scene_id}")
    async def gen_keyframes_scene(slug: str, scene_id: str, n: int = 2,
                                  backend: str | None = None, body: dict = {}):
        """Genera N keyframes para UNA escena con prompt_tweak opcional."""
        from .. import studio

        project, spec, cfg = load(slug)
        if not any(s.id == scene_id for s in spec.scenes):
            raise HTTPException(404, f"Escena '{scene_id}' no encontrada.")
        tweak = (body.get("prompt_tweak") or "").strip()

        async def coro():
            await studio.gen_keyframes_scene(project, spec, cfg, scene_id, n,
                                             prompt_tweak=tweak, backend=backend)
            return {"scene": scene_id, "n": n}

        return jobs.spawn("keyframes", f"{slug}/{scene_id}", coro()).to_dict()

    @app.post("/api/projects/{slug}/candidates/{scene_id}/upload")
    async def upload_candidate(slug: str, scene_id: str, body: UploadBody):
        """Sube una imagen como candidato manual (base64 en JSON).

        Body: { "data": "<base64>", "filename": "foto.png" }
        La imagen entra al pool de candidatos y se selecciona igual que un generado.
        """
        import base64

        from .. import studio

        project, spec, _cfg = load(slug)
        if not any(s.id == scene_id for s in spec.scenes):
            raise HTTPException(404, f"Escena '{scene_id}' no encontrada.")
        raw = body.data.strip()
        if not raw:
            raise HTTPException(422, "Falta 'data' (base64 de la imagen).")
        filename = body.filename or "upload.png"
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(422, f"Formato no soportado: {suffix}. Usá PNG, JPG o WEBP.")
        try:
            data = base64.b64decode(raw)
        except Exception:
            raise HTTPException(422, "El campo 'data' no es base64 válido.")
        dest = studio.add_candidate_upload(project, scene_id, data, suffix)
        return {"url": file_url(dest), "scene": scene_id, "file": dest.name}

    @app.delete("/api/projects/{slug}/candidates/{scene_id}/{idx}")
    def discard_candidate(slug: str, scene_id: str, idx: int):
        """Descarta el candidato `idx` de una escena (T3/D-055): "dejame solo 3".

        Reconcilia la selección por path: si la escena estaba elegida con ese
        candidato, la selección se descarta también."""
        from .. import studio

        project, _spec, _cfg = load(slug)
        try:
            return studio.delete_candidate(project, scene_id, idx)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/projects/{slug}/music/upload")
    async def upload_music(slug: str, body: UploadBody):
        """Sube un archivo de audio como música de fondo (base64 en JSON).

        Body: { "data": "<base64>", "filename": "pista.mp3" }
        """
        import base64

        from .. import studio

        project, spec, _cfg = load(slug)
        raw = body.data.strip()
        if not raw:
            raise HTTPException(422, "Falta 'data' (base64 del audio).")
        filename = body.filename or "music.mp3"
        suffix = Path(filename).suffix.lower() or ".mp3"
        if suffix not in {".mp3", ".wav", ".ogg", ".m4a", ".aac"}:
            raise HTTPException(422, f"Formato no soportado: {suffix}.")
        try:
            data = base64.b64decode(raw)
        except Exception:
            raise HTTPException(422, "El campo 'data' no es base64 válido.")
        dest = project.dir / "cache" / f"music{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        studio.set_project_music(project, spec, dest)
        return {"url": file_url(dest), "file": dest.name}

    @app.post("/api/projects/{slug}/music/generate")
    async def generate_music(slug: str, body: MusicGenBody):
        """Genera música con stable-audio (fal.ai). Job/SSE.

        Body: { "prompt": "...", "duration_s": 30 }
        """
        from .. import studio
        from ..music import generate_music_fal

        project, spec, _cfg = load(slug)
        prompt = body.prompt.strip()
        if not prompt:
            raise HTTPException(422, "Falta 'prompt' para generar la música.")
        duration_s = float(body.duration_s or 30.0)
        s = get_settings()
        if not s.fal_key:
            raise HTTPException(503, "FAL_KEY no configurada.")
        out_path = project.dir / "cache" / "music_generated.wav"

        async def coro():
            dest = await generate_music_fal(prompt, duration_s, out_path, s.fal_key)
            studio.set_project_music(project, spec, dest)
            return {"url": file_url(dest), "file": dest.name}

        return jobs.spawn("music", slug, coro()).to_dict()

    # --- animatic (D-060/D-061): la película en poses, antes de pagar video ---
    @app.get("/api/projects/{slug}/animatic")
    async def get_animatic(slug: str):
        """La tira del animatic en SOLO LECTURA (cero costo): poses por plano +
        costo estimado de completar lo que falta. Mismas cache keys que el render."""
        from ..project import resolve_under
        from ..state import billing_summary
        from ..studio import animatic_strip

        project, spec, cfg = load(slug)
        strip = await animatic_strip(project, spec, cfg)
        missing = sum((0 if e["start"] else 1) + (0 if e["destino"] else 1) for e in strip)
        # D-063: pool de variantes + la elegida, por pose.
        from ..project import read_yaml
        pool = read_yaml(project.dir / "pose_candidates.yaml")
        picks = read_yaml(project.dir / "pose_picks.yaml")
        for e in strip:  # paths -> URLs servibles
            e["start"] = file_url(e["start"]) if e["start"] else None
            e["destino"] = file_url(e["destino"]) if e["destino"] else None
            for which in ("start", "destino"):
                key = f"{e['shot_id']}/{which}"
                e[f"{which}_variants"] = [
                    file_url(resolve_under(project.dir, p))
                    for p in (pool.get(key) or [])
                    if resolve_under(project.dir, p).exists()
                ]
                e[f"{which}_picked"] = key in picks
        return {"strip": strip,
                "total": len(strip),
                "ready": sum(1 for e in strip if e["ready"]),
                "missing_poses": missing,
                "est_missing_cost_usd": round(missing * cfg.storyboard.est_cost_per_image_usd, 4),
                # D-062: la plata visible — segundos pagados (bloques del proveedor) vs usados.
                "billing": billing_summary(spec),
                "est_cost_per_image_usd": cfg.storyboard.est_cost_per_image_usd}

    @app.post("/api/projects/{slug}/animatic")
    async def gen_animatic(slug: str, backend: str | None = None):
        """Genera las poses frontera que falten (job). Cacheado: re-correr = $0."""
        from .. import studio

        project, spec, cfg = load(slug)
        if backend:  # toggle de motor de imagen por llamada (D-051/D-053)
            from ..config import load_config
            cfg = load_config(config_dir, spec.style, backend=backend)

        async def coro():
            sheet = await studio.animatic(project, spec, cfg, open_sheet=False)
            return {"sheet": str(sheet)}

        return jobs.spawn("animatic", slug, coro()).to_dict()

    @app.delete("/api/projects/{slug}/animatic/{shot_id}/{which}")
    async def drop_animatic_pose(slug: str, shot_id: str, which: str):
        """Descarta UNA pose cacheada (curación por excepción, D-060): el próximo
        'generar' regenera solo esa. `which` = start | destino."""
        from ..studio import animatic_strip

        if which not in ("start", "destino"):
            raise HTTPException(400, "which debe ser 'start' o 'destino'.")
        project, spec, cfg = load(slug)
        strip = await animatic_strip(project, spec, cfg)
        entry = next((e for e in strip if e["shot_id"] == shot_id), None)
        if entry is None:
            raise HTTPException(404, f"Plano '{shot_id}' no encontrado.")
        path = entry.get(which)
        if not path:
            return {"dropped": False, "reason": "la pose no existe en cache"}
        p = Path(path)
        if p.exists():
            p.unlink()
        sidecar = p.with_suffix(".meta.json")
        if sidecar.exists():
            sidecar.unlink()
        return {"dropped": True, "shot_id": shot_id, "which": which}

    @app.post("/api/projects/{slug}/animatic/{shot_id}/{which}/variants")
    async def gen_pose_variants(slug: str, shot_id: str, which: str, n: int = 3,
                                backend: str | None = None):
        """[D-063] Genera N variantes de UNA pose (best-of-N: elegir, no solo regenerar)."""
        from .. import studio

        if which not in ("start", "destino"):
            raise HTTPException(400, "which debe ser 'start' o 'destino'.")
        project, spec, cfg = load(slug)
        if backend:
            from ..config import load_config
            cfg = load_config(config_dir, spec.style, backend=backend)

        async def coro():
            paths = await studio.pose_variants(project, spec, cfg, shot_id, which, n=n)
            return {"variants": len(paths)}

        return jobs.spawn("pose_variants", f"{slug}/{shot_id}/{which}", coro()).to_dict()

    @app.post("/api/projects/{slug}/animatic/{shot_id}/{which}/pick")
    async def pick_pose(slug: str, shot_id: str, which: str, body: PosePickBody):
        """[D-063] Fija la variante elegida (key `picked:` -> cascada de cache correcta).

        Body: { "path": "<url o ruta de la variante>" }"""
        from ..studio import record_pose_pick

        project, spec, cfg = load(slug)
        raw = body.path
        # acepta la URL servida (/files/<slug>/...) o una ruta project-relative
        rel = raw.split(f"/files/{slug}/", 1)[-1] if f"/files/{slug}/" in raw else raw
        path = record_pose_pick(project, shot_id, which, Path(rel))
        return {"saved": str(path), "shot_id": shot_id, "which": which}

    @app.post("/api/projects/{slug}/cast")
    async def gen_cast(slug: str, n: int = 4, backend: str | None = None):
        from .. import studio

        project, spec, cfg = load(slug)

        async def coro():
            sheet = await studio.cast(project, spec, cfg, n, open_sheet=False, backend=backend)
            return {"sheet": str(sheet)}

        return jobs.spawn("cast", slug, coro()).to_dict()

    @app.post("/api/projects/{slug}/render")
    async def render(slug: str, body: RenderBody | None = None):
        from .. import studio

        body = body or RenderBody()
        # D-076: mismo default que el CLI (ultra-cheap). El server default-eaba
        # "prod" (ensemble Veo + gate Opus): la misma accion costaba ~15x segun
        # la superficie. Gastar mas es opt-in: body.profile explicito.
        project, spec, cfg = load(slug, profile=body.profile)
        concurrency = int(body.concurrency or 1)

        async def coro():
            run, final, totals = await studio.render(project, spec, cfg,
                                                     concurrency=concurrency)
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
    def pick(slug: str, body: PicksBody):
        from ..studio import record_picks

        project, _spec, _cfg = load(slug)
        path = record_picks(project, dict(body.picks))
        return {"saved": str(path)}

    @app.post("/api/projects/{slug}/pick-cast")
    def pick_cast(slug: str, body: PicksBody):
        from ..studio import record_cast_picks

        project, _spec, _cfg = load(slug)
        path = record_cast_picks(project, dict(body.picks))
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
        updates = {env_name: body[attr] for attr, env_name in _KEYS.items()
                   if attr in body and body[attr] is not None}
        env.write_text("\n".join(merge_env_lines(lines, updates)) + "\n", encoding="utf-8")
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
