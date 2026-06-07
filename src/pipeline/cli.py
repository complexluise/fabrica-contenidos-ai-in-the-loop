"""CLI - cablea todas las capas del MVP.

    pipeline run briefs/example.yaml --style lego --format 9:16
    -> out/final_9x16.mp4 + out/run_report.json
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import typer
from rich.console import Console

from .assemble import concat_clips
from .classifier import classify
from .config import load_config
from .contracts import Scene
from .deliver import reframe
from .gate import VLMGate
from .ingest import load_brief
from .keyframe import KeyframeGenerator
from .providers.base import build_provider
from .strategies.router import SmartRouter
from .telemetry import SceneRecord, Telemetry

app = typer.Typer(add_completion=False, help="Pipeline de video IA multi-modelo.")
console = Console()


@app.callback()
def _main(
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Logs detallados (DEBUG, con tracebacks)."
    ),
) -> None:
    """Pipeline de video IA. Usa 'pipeline -v <cmd>' para ver el progreso al detalle."""
    from .logging_setup import setup_logging

    setup_logging(verbose)


async def _run_async(
    brief: Path, config_dir: Path, style: str, fmt: str, out_dir: Path
) -> Path:
    run_id = uuid.uuid4().hex[:8]
    cfg = load_config(config_dir, style)
    providers = [build_provider(p) for p in cfg.providers.values()]
    gate = VLMGate(cfg.routing.thresholds)
    keyframer = KeyframeGenerator(cfg.style)
    router = SmartRouter(max_retries=1)
    telemetry = Telemetry(run_id)

    scenes: list[Scene] = load_brief(brief)
    console.print(f"[bold]Run {run_id}[/] · {len(scenes)} escenas · estilo {style}")

    clips: list[Path] = []
    for scene in scenes:
        scene.class_ = scene.class_ or classify(scene)
        console.print(f"  · {scene.id} [{scene.class_}] -> keyframe")
        scene.keyframe = await keyframer.generate(scene)

        result = await router.run(scene, providers, gate)
        clips.append(result.video_path)

        telemetry.record(
            SceneRecord(
                run_id=run_id,
                scene_id=scene.id,
                provider=result.provider,
                strategy=router.name,
                scene_class=scene.class_,
                cost_usd=result.cost_usd,
                latency_s=result.latency_s,
                attempt=result.raw_meta.get("attempts", 1),
                passed=result.raw_meta.get("gate_passed", True),
            )
        )
        console.print(
            f"    {result.provider} · ${result.cost_usd:.3f} · {result.latency_s:.1f}s"
            f" · gate={'ok' if result.raw_meta.get('gate_passed', True) else 'fail'}"
        )

    stitched = concat_clips(clips, out_dir / "_stitched.mp4")
    final = reframe(stitched, out_dir / f"final_{fmt.replace(':', 'x')}.mp4", fmt)

    report = telemetry.write_report(out_dir / "run_report.json")
    telemetry.close()

    totals = telemetry.totals()
    console.print(
        f"\n[bold green]Listo[/] {final}\n"
        f"  costo total: ${totals['total_cost_usd']:.3f}"
        f" · latencia: {totals['total_latency_s']:.1f}s · reporte: {report}"
    )
    return final


async def _run_project_async(slug: str, projects_root: Path, config_dir: Path,
                            profile: str = "prod", concurrency: int = 1) -> Path:
    from .project import Project, load_project_spec
    from .runner import run_project

    project = Project(slug, root=projects_root)
    spec = load_project_spec(project.spec_path)
    cfg = load_config(config_dir, spec.style, profile=profile)
    console.print(
        f"[bold]Proyecto {slug}[/] · {len(spec.scenes)} escenas"
        f" · estilo {spec.style} · perfil {profile} · concurrencia {concurrency}"
    )

    run, final, totals = await run_project(project, spec, cfg, concurrency=concurrency)
    console.print(
        f"\n[bold green]Listo[/] {final}\n"
        f"  run {run.run_id} · costo: ${totals['total_cost_usd']:.3f}"
        f" · cache hits: {totals['cache_hits']}/{totals['attempts']}"
        f" · manifiesto: {run.manifest_path}"
    )
    return final


def _load_project(slug: str, projects_root: Path, config_dir: Path):
    from .project import Project, load_project_spec
    from .studio import apply_casting, load_casting

    project = Project(slug, root=projects_root)
    spec = load_project_spec(project.spec_path)
    cfg = load_config(config_dir, spec.style)
    apply_casting(spec.characters, load_casting(project))  # caras elegidas en casting
    return project, spec, cfg


@app.command()
def cast(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    n: int = typer.Option(4, "--n", help="Caras candidatas por personaje."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Diseña caras de personaje (multi-imagen + prompt) y abre la hoja de contactos."""
    from .studio import cast as cast_characters

    proj, spec, cfg = _load_project(project, projects_dir, config_dir)
    designed = [n for n, c in spec.characters.items() if c.design]
    console.print(f"[bold]{project}[/] · casting de {designed} × {n} candidatos…")
    sheet = asyncio.run(cast_characters(proj, spec, cfg, n))
    console.print(
        f"\n[bold green]Listo[/] hoja de contactos: {sheet}\n"
        f"  elige con: [cyan]pipeline pick-cast {project} "
        + " ".join(f"{c}=N" for c in designed) + "[/]"
    )


@app.command(name="pick-cast")
def pick_cast(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    selections: list[str] = typer.Argument(
        None, help="Elecciones personaje=indice del flujo de candidatos (p.ej. juan=2)."),
    face: list[str] = typer.Option(
        None, "--face",
        help="Cara directa personaje=ruta (repetible), sin pasar por cast/candidatos (D-025).",
    ),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Fija la cara canónica por personaje: por índice de candidato o --face directa."""
    from .studio import parse_overrides, parse_picks, record_cast_picks, set_cast_faces

    proj, _spec, _cfg = _load_project(project, projects_dir, config_dir)
    if face:
        faces = parse_overrides(face)
        path = set_cast_faces(proj, faces)
        console.print(f"[bold green]Caras fijadas (directas)[/] {list(faces)} -> {path}")
    if selections:
        picks = parse_picks(selections)
        path = record_cast_picks(proj, picks)
        console.print(f"[bold green]Casting fijado[/] {picks} -> {path}")
    if not face and not selections:
        console.print("[yellow]Nada que fijar.[/] Pasa personaje=indice o --face personaje=ruta.")


@app.command()
def keyframes(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    n: int = typer.Option(4, "--n", help="Candidatos de keyframe por escena."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Genera N keyframes/escena y abre la hoja de contactos para elegir."""
    from .studio import gen_keyframes

    proj, spec, cfg = _load_project(project, projects_dir, config_dir)
    console.print(f"[bold]{project}[/] · {len(spec.scenes)} escenas × {n} candidatos…")
    sheet = asyncio.run(gen_keyframes(proj, spec, cfg, n))
    console.print(
        f"\n[bold green]Listo[/] hoja de contactos: {sheet}\n"
        f"  elige con: [cyan]pipeline pick {project} "
        + " ".join(f"{s.id}=N" for s in spec.scenes) + "[/]"
    )


@app.command()
def pick(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    selections: list[str] = typer.Argument(..., help="Elecciones escena=indice (p.ej. s1=2)."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Registra el keyframe elegido por escena."""
    from .studio import parse_picks, record_picks

    proj, _spec, _cfg = _load_project(project, projects_dir, config_dir)
    picks = parse_picks(selections)
    path = record_picks(proj, picks)
    console.print(f"[bold green]Guardado[/] {picks} -> {path}")


@app.command()
def render(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    keyframe: list[str] = typer.Option(
        None, "--keyframe",
        help="Keyframe directo escena=ruta (repetible). Gana sobre selections.yaml (D-025).",
    ),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Genera el video con los keyframes elegidos (o inyectados con --keyframe)."""
    from .studio import parse_overrides, render as render_project

    proj, spec, cfg = _load_project(project, projects_dir, config_dir)
    overrides = parse_overrides(keyframe) if keyframe else {}
    if overrides:
        console.print(f"[bold]{project}[/] · render · keyframes directos: {list(overrides)}")
    else:
        console.print(f"[bold]{project}[/] · render con keyframes elegidos…")
    run, final, totals = asyncio.run(render_project(proj, spec, cfg, keyframe_overrides=overrides))
    console.print(
        f"\n[bold green]Listo[/] {final}\n"
        f"  run {run.run_id} · costo: ${totals['total_cost_usd']:.3f}"
        f" · cache hits: {totals['cache_hits']}/{totals['attempts']}"
    )


@app.command()
def studio(
    host: str = typer.Option("127.0.0.1", help="Host del servidor local."),
    port: int = typer.Option(8765, help="Puerto."),
    no_open: bool = typer.Option(False, "--no-open", help="No abrir el navegador."),
    projects_dir: Path = typer.Option(Path("projects")),
    config_dir: Path = typer.Option(Path("config")),
):
    """[D-031] Levanta el Studio local (UI web) sobre el pipeline."""
    import os
    import threading
    import webbrowser

    try:
        import uvicorn
    except ImportError:
        console.print("[red]Falta el extra 'studio'.[/] Instala: [cyan]uv sync --extra studio[/]")
        raise typer.Exit(1)

    os.environ["STUDIO_PROJECTS_DIR"] = str(projects_dir)
    os.environ["STUDIO_CONFIG_DIR"] = str(config_dir)
    url = f"http://{host}:{port}"
    console.print(f"[bold green]Studio[/] en [cyan]{url}[/]  (Ctrl+C para salir)")
    if not no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("pipeline.server.app:app", host=host, port=port, log_level="warning")


@app.command()
def export(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[L8] Arma el bundle de edición humana (media/frames/guion/srt) desde el último run."""
    from .export import export_bundle

    proj, spec, _cfg = _load_project(project, projects_dir, config_dir)
    out = export_bundle(proj, spec)
    console.print(
        f"\n[bold green]Bundle listo[/] {out}\n"
        f"  media/ (videos+voces+musica) · frames/ · rough_cut.mp4 · subtitulos.srt · guion.md"
    )


@app.command()
def run(
    project: str = typer.Argument(..., help="Slug del proyecto (projects/<slug>/project.yaml) o, con --brief, ignorado."),
    brief: Path = typer.Option(None, "--brief", help="Modo smoke: corre un brief YAML suelto a out/ (sin proyecto/cache)."),
    style: str = typer.Option("lego", help="Style slot (solo modo --brief)."),
    fmt: str = typer.Option("9:16", "--format", help="Formato de salida (solo modo --brief)."),
    profile: str = typer.Option("prod", "--profile", help="Perfil de calidad: prod (ensemble/calidad) o proto (router/barato). D-038."),
    concurrency: int = typer.Option(1, "--concurrency", help="Escenas en vuelo simultaneo (D-039). Default 1 = serial."),
    config_dir: Path = typer.Option(Path("config"), help="Directorio de config."),
    projects_dir: Path = typer.Option(Path("projects"), help="Raíz de proyectos."),
    out_dir: Path = typer.Option(Path("out"), help="Salida del modo --brief."),
):
    """Genera un video one-shot. --profile proto para iterar barato; --profile prod para produccion final."""
    if brief is not None:
        asyncio.run(_run_async(brief, config_dir, style, fmt, out_dir))
    else:
        asyncio.run(_run_project_async(project, projects_dir, config_dir,
                                       profile=profile, concurrency=concurrency))


if __name__ == "__main__":
    app()
