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

_DEFAULT_PROFILE = "fal-ultra-cheap"


def _cost_summary(label: str, n: int, est_per_scene: float, actual_usd: float | None = None) -> str:
    """Linea de costo no intrusiva al final de cada subcomando (D-052)."""
    est = est_per_scene * n
    parts = [f"[cost] {label} {n}  est ${est:.3f}"]
    if actual_usd is not None:
        parts.append(f"actual ${actual_usd:.3f}")
    return "  |  ".join(parts)


def _print_advisories(spec, cfg) -> None:
    """Avisos NO bloqueantes del storyboard antes de generar (D-055/D-057): una línea
    por aviso, en amarillo. No invalida — solo da visibilidad de lo que falta."""
    from .state import signing_advisories
    for a in signing_advisories(spec, cfg.routing, cfg.providers):
        console.print(f"[yellow]aviso[/] {a['scene']}: {a['msg']}")


def _is_balance_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("402", "payment required", "insufficient", "balance", "credits"))


def _balance_tip_render(profile: str) -> str:
    alt = "gemini-budget" if not profile.startswith("gemini") else "fal-ultra-cheap"
    return f"[yellow]Saldo agotado en render. Cambia con:[/] [cyan]--profile {alt}[/]"


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
    keyframer = KeyframeGenerator(cfg.style, fmt=fmt)  # D-071
    router = SmartRouter(max_retries=1)
    telemetry = Telemetry(run_id)

    scenes: list[Scene] = load_brief(brief)
    console.print(f"[bold]Run {run_id}[/] - {len(scenes)} escenas - estilo {style}")

    clips: list[Path] = []
    for scene in scenes:
        scene.class_ = scene.class_ or classify(scene)
        console.print(f"  - {scene.id} [{scene.class_}] -> keyframe")
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
            f"    {result.provider} - ${result.cost_usd:.3f} - {result.latency_s:.1f}s"
            f" - gate={'ok' if result.raw_meta.get('gate_passed', True) else 'fail'}"
        )

    stitched = concat_clips(clips, out_dir / "_stitched.mp4")
    final = reframe(stitched, out_dir / f"final_{fmt.replace(':', 'x')}.mp4", fmt)

    report = telemetry.write_report(out_dir / "run_report.json")
    telemetry.close()

    totals = telemetry.totals()
    console.print(
        f"\n[bold green]Listo[/] {final}\n"
        f"  costo total: ${totals['total_cost_usd']:.3f}"
        f" - latencia: {totals['total_latency_s']:.1f}s - reporte: {report}"
    )
    return final


async def _run_project_async(slug: str, projects_root: Path, config_dir: Path,
                            profile: str = _DEFAULT_PROFILE, concurrency: int = 1,
                            voice: str | None = None) -> Path:
    from .project import Project, load_project_spec
    from .runner import run_project

    project = Project(slug, root=projects_root)
    spec = load_project_spec(project.spec_path)
    cfg = load_config(config_dir, spec.style, profile=profile,
                      voice_backend=voice or spec.voice_backend)  # D-058
    console.print(
        f"[bold]Proyecto {slug}[/] - {len(spec.scenes)} escenas"
        f" - estilo {spec.style} - perfil {profile} - concurrencia {concurrency}"
    )

    run, final, totals = await run_project(project, spec, cfg, concurrency=concurrency)
    actual = totals["total_cost_usd"]
    console.print(
        f"\n[bold green]Listo[/] {final}\n"
        f"  run {run.run_id} - costo: ${actual:.3f}"
        f" - cache hits: {totals['cache_hits']}/{totals['attempts']}"
        f" - manifiesto: {run.manifest_path}"
    )
    console.print(_cost_summary("escenas", len(spec.scenes),
                                cfg.profile.est_cost_per_scene_usd, actual))
    return final


def _load_project(slug: str, projects_root: Path, config_dir: Path,
                  profile: str = _DEFAULT_PROFILE, backend: str | None = None,
                  voice: str | None = None):
    from .project import Project, load_project_spec
    from .studio import apply_casting, load_casting

    project = Project(slug, root=projects_root)
    spec = load_project_spec(project.spec_path)
    # D-053/D-058: backend de imagen y de voz del spec si no se pasan explícitos por CLI
    resolved_backend = backend or spec.storyboard_backend
    resolved_voice = voice or spec.voice_backend
    cfg = load_config(config_dir, spec.style, profile=profile, backend=resolved_backend,
                      voice_backend=resolved_voice)
    apply_casting(spec.characters, load_casting(project))  # caras elegidas en casting
    return project, spec, cfg


@app.command()
def cast(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    n: int = typer.Option(4, "--n", help="Caras candidatas por personaje."),
    backend: str = typer.Option(None, "--backend", help="Backend de imagen: fal (default) o google (D-053)."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Diseña caras de personaje (multi-imagen + prompt) y abre la hoja de contactos."""
    from .studio import cast as cast_characters

    try:
        proj, spec, cfg = _load_project(project, projects_dir, config_dir, backend=backend)
        designed = [n for n, c in spec.characters.items() if c.design]
        console.print(f"[bold]{project}[/] - casting de {designed} x {n} candidatos - backend {cfg.storyboard.name}...")
        sheet = asyncio.run(cast_characters(proj, spec, cfg, n))
        n_chars = len(designed)
        console.print(
            f"\n[bold green]Listo[/] hoja de contactos: {sheet}\n"
            f"  elige con: [cyan]pipeline pick-cast {project} "
            + " ".join(f"{c}=N" for c in designed) + "[/]"
        )
        console.print(_cost_summary("caras", n_chars * n, cfg.storyboard.est_cost_per_image_usd))
    except Exception as exc:
        if _is_balance_error(exc):
            alt = "google" if cfg.storyboard.name == "fal" else "fal"
            console.print(f"[yellow]Saldo agotado. Cambia con:[/] [cyan]--backend {alt}[/]")
        raise


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
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Requests simultaneos (default 5)."),
    backend: str = typer.Option(None, "--backend", help="Backend de imagen: fal (default) o google (D-053)."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Genera N keyframes/escena en paralelo y abre la hoja de contactos."""
    from .studio import gen_keyframes

    try:
        proj, spec, cfg = _load_project(project, projects_dir, config_dir, backend=backend)
        total = len(spec.scenes) * n
        console.print(
            f"[bold]{project}[/] - {len(spec.scenes)} escenas x {n} candidatos = {total} imagenes"
            f" | backend {cfg.storyboard.name} | concurrencia {concurrency}"
        )
        _print_advisories(spec, cfg)  # D-057: visibilidad antes de gastar
        sheet = asyncio.run(gen_keyframes(proj, spec, cfg, n, concurrency=concurrency))
        console.print(
            f"\n[bold green]Listo[/] hoja de contactos: {sheet}\n"
            f"  elige con: [cyan]pipeline pick {project} "
            + " ".join(f"{s.id}=N" for s in spec.scenes) + "[/]"
        )
        console.print(_cost_summary("keyframes", total, cfg.storyboard.est_cost_per_image_usd))
    except Exception as exc:
        if _is_balance_error(exc):
            alt = "google" if cfg.storyboard.name == "fal" else "fal"
            console.print(f"[yellow]Saldo agotado. Cambia con:[/] [cyan]--backend {alt}[/]")
        raise


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
def takes(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    shot: str = typer.Option(None, "--shot", help="Filtra a un plano (p.ej. s2)."),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop · D-074] Lista las tomas de cada plano del último render
    (la titular del corte + las alternativas, con sus scores del gate)."""
    from .project import Project
    from .studio import shot_takes

    proj = Project(slug=project, root=projects_dir)
    all_takes = shot_takes(proj, shot)
    if not all_takes:
        console.print("[yellow]Sin render todavía[/] (o el plano no existe). Corre `render` primero.")
        raise typer.Exit(1)
    for sid, items in all_takes.items():
        console.print(f"[bold]{sid}[/]")
        for i, t in enumerate(items):
            gs = t.get("gate_scores") or {}
            score = ", ".join(f"{k}={v:.2f}" for k, v in gs.items()) or "sin score"
            mark = " [green](elegida)[/]" if t.get("picked") else ""
            vp = t.get("video_path") or t.get("video_key") or "?"
            console.print(f"  [{i}] {t.get('role', '?'):<11} {t.get('provider', '?'):<10} {score}{mark}")
            console.print(f"      {vp}")
    console.print("\n  fija una con: [cyan]pipeline pick-take "
                  f"{project} <shot>=<ruta del .mp4>[/]")


@app.command(name="pick-take")
def pick_take(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    selections: list[str] = typer.Argument(..., help="Elecciones plano=ruta (p.ej. s2=cache/takes/abc.mp4)."),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop · D-074] Fija la TOMA elegida de un plano: manda sobre el
    ranking del gate en el próximo render (cache-hit, $0)."""
    from .project import Project
    from .studio import record_take_pick

    proj = Project(slug=project, root=projects_dir)
    for sel in selections:
        if "=" not in sel:
            console.print(f"[red]Formato inválido:[/] '{sel}' (usa plano=ruta).")
            raise typer.Exit(1)
        sid, _, raw = sel.partition("=")
        path = record_take_pick(proj, sid.strip(), Path(raw.strip()))
        console.print(f"[bold green]Guardado[/] {sid} -> {raw} ({path.name})")


@app.command()
def animatic(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    backend: str = typer.Option(None, "--backend", help="Backend de imagen: fal (default) o google (D-053)."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop · D-060] La película en poses: genera las poses frontera
    (apertura -> destino) de cada plano y abre la hoja de contactos, ANTES de pagar video."""
    from .studio import animatic as build_animatic

    try:
        proj, spec, cfg = _load_project(project, projects_dir, config_dir, backend=backend)
        from .project import effective_shots
        n_shots = sum(len(s.shots) or 1 for s in spec.scenes)
        # D-070: las aperturas solo existen para planos `lands` (los que interpolan).
        n_lands = sum(1 for s in spec.scenes for sh in effective_shots(s) if sh.lands)
        n_poses = n_shots + n_lands
        console.print(f"[bold]{project}[/] - animatic: {n_shots} destinos + {n_lands} aperturas"
                      f" | backend {cfg.storyboard.name}")
        _print_advisories(spec, cfg)  # D-057: visibilidad antes de gastar
        sheet = asyncio.run(build_animatic(proj, spec, cfg))
        console.print(f"\n[bold green]Listo[/] animatic: {sheet}\n"
                      "  si una pose no convence: ajusta el ancla (pick) o el seed del plano y re-corre.")
        console.print(_cost_summary("poses", n_poses, cfg.storyboard.est_cost_per_image_usd))
    except Exception as exc:
        if _is_balance_error(exc):
            console.print("[yellow]Saldo agotado.[/] Cambia con: [cyan]--backend google[/]")
        raise


@app.command()
def render(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    keyframe: list[str] = typer.Option(
        None, "--keyframe",
        help="Keyframe directo escena=ruta (repetible). Gana sobre selections.yaml (D-025).",
    ),
    profile: str = typer.Option(_DEFAULT_PROFILE, "--profile", help="Perfil de IA (D-052)."),
    voice: str = typer.Option(None, "--voice", help="Backend de voz: kokoro (default) o elevenlabs (D-058)."),
    concurrency: int = typer.Option(1, "--concurrency", "-c",
                                    help="Planos de video en paralelo (D-039/D-060). Default 1 = serial."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[AI-in-the-Loop] Genera el video con los keyframes elegidos (o inyectados con --keyframe)."""
    from .studio import parse_overrides, render as render_project

    try:
        proj, spec, cfg = _load_project(project, projects_dir, config_dir, profile, voice=voice)
        overrides = parse_overrides(keyframe) if keyframe else {}
        if overrides:
            console.print(f"[bold]{project}[/] - render - perfil {profile} - keyframes directos: {list(overrides)}")
        else:
            console.print(f"[bold]{project}[/] - render con keyframes elegidos - perfil {profile}...")
        _print_advisories(spec, cfg)  # D-057: visibilidad antes de gastar
        run, final, totals = asyncio.run(render_project(proj, spec, cfg, keyframe_overrides=overrides,
                                                        concurrency=concurrency))
        actual = totals["total_cost_usd"]
        console.print(
            f"\n[bold green]Listo[/] {final}\n"
            f"  run {run.run_id} - costo: ${actual:.3f}"
            f" - cache hits: {totals['cache_hits']}/{totals['attempts']}"
        )
        console.print(_cost_summary("escenas", len(spec.scenes),
                                    cfg.profile.est_cost_per_scene_usd, actual))
    except Exception as exc:
        if _is_balance_error(exc):
            console.print(_balance_tip_render(profile))
        raise


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
        f"  media/ (videos+voces+musica) - frames/ - rough_cut.mp4 - subtitulos.srt - guion.md"
    )


@app.command()
def describe(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[L10] Ojos: Haiku describe/evalua cada plano del bundle -> descriptions.yaml (D-041)."""
    from .describe import describe_bundle

    proj, _spec, _cfg = _load_project(project, projects_dir, config_dir)
    console.print(f"[bold]{project}[/] - describiendo planos con Haiku...")
    path = describe_bundle(proj)
    console.print(
        f"\n[bold green]Listo[/] {path}\n"
        f"  por plano: description - on_message - usable - issues"
    )


@app.command()
def graphics(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[L10] Artista: motion graphics (movis) -> export/graphics/ (lower-thirds, titulo, cierre) (D-042)."""
    try:
        import movis  # noqa: F401
    except ImportError:
        console.print("[red]Falta el extra 'edit'.[/] Instala: [cyan]uv sync --extra edit[/]")
        raise typer.Exit(1)
    from .graphics import render_graphics

    proj, spec, _cfg = _load_project(project, projects_dir, config_dir)
    console.print(f"[bold]{project}[/] - generando motion graphics con movis...")
    out = render_graphics(proj, spec)
    console.print(
        f"\n[bold green]Graphics listos[/] {out}\n"
        f"  lower-thirds por plano (lt_<base>.png, con alpha) - title.mp4 - end.mp4"
    )


@app.command()
def prompts(
    project: str = typer.Argument(..., help="Slug del proyecto."),
    scene: str = typer.Option(None, "--scene", help="Compilar solo esta escena (id). Default: todas las desactualizadas."),
    force: bool = typer.Option(False, "--force", help="Recompila tambien las en-sintonia y las marcadas como manual."),
    config_dir: Path = typer.Option(Path("config")),
    projects_dir: Path = typer.Option(Path("projects")),
):
    """[L1.5] Compila el prompt visual de cada escena desde la narrativa (Haiku) (D-046)."""
    from .project import write_spec
    from .prompt_compile import sync_scene_prompt

    proj, spec, _cfg = _load_project(project, projects_dir, config_dir)
    targets = [s for s in spec.scenes if (scene is None or s.id == scene)]
    if scene and not targets:
        console.print(f"[red]Escena '{scene}' no encontrada.[/]")
        raise typer.Exit(1)

    todo = [s for s in targets if (scene is not None or force or s.prompt_stale)]
    if not todo:
        console.print("[green]Todo en sintonia.[/] Nada que compilar.")
        return

    console.print(f"[bold]{project}[/] - compilando {len(todo)} prompt(s) desde la narrativa...")
    for s in todo:
        sync_scene_prompt(s, spec.characters)
        console.print(f"  - {s.id}: {s.prompt[:72]}...")
    write_spec(spec, proj.spec_path)
    console.print(f"\n[bold green]Listo[/] {proj.spec_path} - {len(todo)} prompt(s) en sintonia.")


@app.command()
def run(
    project: str = typer.Argument(..., help="Slug del proyecto (projects/<slug>/project.yaml) o, con --brief, ignorado."),
    brief: Path = typer.Option(None, "--brief", help="Modo smoke: corre un brief YAML suelto a out/ (sin proyecto/cache)."),
    style: str = typer.Option("lego", help="Style slot (solo modo --brief)."),
    fmt: str = typer.Option("9:16", "--format", help="Formato de salida (solo modo --brief)."),
    profile: str = typer.Option(_DEFAULT_PROFILE, "--profile", help="Perfil de IA: fal-ultra-cheap (default), fal-standard, prod, gemini-budget... (D-052)."),
    voice: str = typer.Option(None, "--voice", help="Backend de voz: kokoro (default) o elevenlabs (D-058)."),
    concurrency: int = typer.Option(1, "--concurrency", help="Escenas en vuelo simultaneo (D-039). Default 1 = serial."),
    config_dir: Path = typer.Option(Path("config"), help="Directorio de config."),
    projects_dir: Path = typer.Option(Path("projects"), help="Raiz de proyectos."),
    out_dir: Path = typer.Option(Path("out"), help="Salida del modo --brief."),
):
    """Genera un video. Default: perfil ultra-cheap para iterar barato; --profile prod para produccion."""
    try:
        if brief is not None:
            asyncio.run(_run_async(brief, config_dir, style, fmt, out_dir))
        else:
            asyncio.run(_run_project_async(project, projects_dir, config_dir,
                                           profile=profile, concurrency=concurrency, voice=voice))
    except Exception as exc:
        if _is_balance_error(exc):
            console.print(_balance_tip_render(profile))
        raise


if __name__ == "__main__":
    app()
