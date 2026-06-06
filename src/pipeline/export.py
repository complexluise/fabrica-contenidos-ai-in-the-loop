"""L8 - Export bundle para edición humana (D-029).

`pipeline export <slug>` arma `projects/<slug>/export/` desde el último run:
`media/` (videos limpios + voces + música), `frames/` (keyframes), `rough_cut.mp4`,
`subtitulos.srt` y `guion.md` (onboarding + tabla de planos). El `final.mp4` es el
rough cut, no el corte definitivo: la editora hace el corte real.

`_ts`, `numbered`, `srt_from_timeline` y `render_guion` son lógica pura (core
testeable); `export_bundle` es I/O (copia de archivos, smoke).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from .assemble import trim_to
from .project import Project, ProjectSpec

logger = logging.getLogger(__name__)


def _text(v) -> str:
    """Texto seguro de un campo del manifest. Tolera manifests viejos donde
    `voiceover` se guardaba como bool (pre-D-028/D-029) -> no string = ''."""
    return v.strip() if isinstance(v, str) else ""


def _ts(seconds: float) -> str:
    """Segundos -> 'HH:MM:SS,mmm' (tiempo de SRT)."""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def numbered(planos: list[dict]) -> list[dict]:
    """Asigna el orden global `n` y el nombre base `NN_<id>` a cada plano (D-029)."""
    return [{**p, "n": i, "base": f"{i:02d}_{p['id']}"} for i, p in enumerate(planos, start=1)]


def srt_from_timeline(planos: list[dict]) -> str:
    """SRT sincronizado: la voz de cada plano, timeada por la suma de duraciones.

    El timeline avanza con TODOS los planos; solo los que tienen voz emiten un cue.
    """
    cues: list[str] = []
    t = 0.0
    idx = 0
    for p in planos:
        dur = float(p.get("duration_s") or 0)
        text = _text(p.get("voiceover"))
        if text:
            idx += 1
            cues.append(f"{idx}\n{_ts(t)} --> {_ts(t + dur)}\n{text}\n")
        t += dur
    return "\n".join(cues)


def _fm(s: str) -> str:
    """Scalar YAML seguro para el frontmatter (una línea, comillas escapadas)."""
    return '"' + (s or "").replace('"', "'").replace("\n", " ").strip() + '"'


def _group_by_scene(planos: list[dict]) -> list[tuple[str, list[dict]]]:
    """Agrupa planos por escena preservando el orden de aparición."""
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for p in planos:
        key = p.get("scene") or p["id"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)
    return [(k, groups[k]) for k in order]


def render_guion(spec: ProjectSpec, planos: list[dict]) -> str:
    """`guion.md` (D-030): documento autoexplicativo — sinopsis + personajes + el guion
    beat-por-beat + tabla por plano + organización/definiciones. Arranca con frontmatter
    (metadata para el conversor a .docx). Lo importante primero, definiciones al final."""
    title = spec.title or spec.slug
    total = sum(float(p.get("duration_s") or 0) for p in planos)
    subtitle = f"{spec.style} · {spec.format} · ~{total:.0f}s · {len(planos)} planos"
    scene_by_id = {s.id: s for s in spec.scenes}

    L = ["---", f"title: {_fm(title + ' — guion y materiales')}",
         f"subtitle: {_fm(subtitle)}", f"footer: {_fm(title)}", "---", "",
         f"# {title}", "", f"*{subtitle}*", ""]

    if spec.brief:
        L += ["## Sinopsis", "", spec.brief.strip(), ""]

    if spec.characters:
        L += ["## Personajes", ""]
        L += [f"- **{name}**" for name in spec.characters]
        L += [""]

    # --- el guion, beat por beat (legible como libreto) ---
    L += ["## Guion", ""]
    for key, ps in _group_by_scene(planos):
        beat = _text(ps[0].get("beat"))
        L += [f"### Escena {key}" + (f" · {beat}" if beat else ""), ""]
        sc = scene_by_id.get(key)
        if sc is not None and sc.prompt:
            desc = sc.prompt.strip()
            L += [f"*{desc[:237].rstrip() + '...' if len(desc) > 240 else desc}*", ""]
        for p in ps:
            framing = _text(p.get("framing")) or "plano base"
            line = f"- **Plano {p['n']:02d}** — *{framing}*"
            voz = _text(p.get("voiceover"))
            if voz:
                line += f' — "{voz}"'
            L.append(line)
        L.append("")

    # --- desglose técnico por plano (para edición) ---
    L += ["## Desglose por plano (para edición)", "",
          "| # | archivo | beat | dur | qué se ve | voz | texto en pantalla |",
          "|---|---|---|---|---|---|---|"]
    for p in planos:
        voz = _text(p.get("voiceover")).replace("|", "/") or "—"
        cap = _text(p.get("caption")).replace("|", "/") or "—"
        framing = _text(p.get("framing")).replace("|", "/") or "(plano base)"
        beat = _text(p.get("beat")) or _text(p.get("scene")) or ""
        dur = float(p.get("duration_s") or 0)
        L.append(f"| {p['n']:02d} | media/{p['base']}.mp4 | {beat} | {dur:.0f}s "
                 f"| {framing} | {voz} | {cap} |")
    L += [""]

    # --- onboarding + definiciones (al final) ---
    L += ["## Cómo está organizado", "",
          "- **media/** — los videos + las voces (mismo nombre = mismo plano) + la música.",
          "- **frames/** — la imagen base (keyframe) de cada plano.",
          "- **rough_cut.mp4** — cómo proponemos el orden y el ritmo (NO es el corte final).",
          "- **subtitulos.srt** — subtítulos ya sincronizados.", "",
          "## Definiciones (por si hay dudas)", "",
          "- **Plano**: una toma/clip. El video se arma juntando planos en orden.",
          "- **Beat / escena**: un momento del guion; puede tener varios planos.",
          "- **Keyframe**: la imagen base de la que sale cada plano (carpeta `frames/`).",
          "- **Rough cut**: el corte automático de referencia, no el definitivo.",
          "- **Voz**: lo que se narra en ese plano (el audio está en `media/`).", ""]
    return "\n".join(L)


def _maybe_docx(md_path: Path) -> None:
    """Best-effort (D-030): si hay node + el conversor, genera el .docx junto al .md.

    Python no depende de Node: si falta node o el conversor no está instalado
    (`pnpm install`), se omite el .docx sin romper el export.
    """
    node = shutil.which("node")
    convert = Path(__file__).resolve().parent.parent / "md_to_docs" / "convert.js"
    if not node or not convert.exists():
        logger.info("guion.docx omitido (sin node o conversor): instala src/md_to_docs (pnpm install).")
        return
    try:
        subprocess.run([node, str(convert), str(md_path), str(md_path.with_suffix(".docx"))],
                       check=True, capture_output=True, timeout=120)
        logger.info("guion.docx generado.")
    except Exception as exc:  # noqa: BLE001 — best-effort: el .md ya quedó
        logger.warning("No se pudo generar guion.docx (best-effort): %s", exc)


def _reset_dir(d: Path) -> None:
    """Borra el directorio para empezar limpio. En Windows un archivo abierto
    (un .docx, el antivirus) puede tener un lock transitorio -> reintenta y, en
    el peor caso, ignora errores (los archivos se sobrescriben igual)."""
    for _ in range(3):
        if not d.exists():
            return
        try:
            shutil.rmtree(d)
            return
        except OSError:
            time.sleep(0.3)
    shutil.rmtree(d, ignore_errors=True)


def _manifest_planos(run) -> list[dict]:
    data = yaml.safe_load(run.manifest_path.read_text(encoding="utf-8")) or {}
    return data.get("scenes") or []


def export_bundle(project: Project, spec: ProjectSpec) -> Path:
    """Arma `projects/<slug>/export/` desde el último run. Devuelve la carpeta. I/O (smoke)."""
    run = project.latest_run()
    if run is None or not run.manifest_path.exists():
        raise RuntimeError(
            f"No hay runs para '{project.slug}'. Corre 'pipeline render {project.slug}' primero.")

    planos = numbered(_manifest_planos(run))
    if not planos:
        raise RuntimeError("El manifest del último run no tiene planos.")
    if not any(p.get("duration_s") for p in planos):
        logger.warning("El último run (%s) es anterior al cambio de planos/export: faltan "
                       "duraciones, voz y keyframes. Re-renderiza el proyecto (cache hits, ~$0) "
                       "para un bundle completo.", run.run_id)

    export_dir = project.dir / "export"
    _reset_dir(export_dir)  # export limpio (refleja el último run); robusto a locks de Windows
    media = export_dir / "media"
    frames = export_dir / "frames"
    media.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)

    for p in planos:
        base = p["base"]
        dur = float(p.get("duration_s") or 0)
        clip = project.cache_lookup("clips", p["video_key"], ".mp4")
        if clip is not None:  # video limpio (caché) recortado a la duración del plano
            trimmed = trim_to(clip, export_dir / "_t.mp4", dur) if dur > 0 else clip
            shutil.copyfile(trimmed, media / f"{base}.mp4")
            if trimmed != clip:
                Path(trimmed).unlink(missing_ok=True)
        vo = p.get("vo_path")
        if vo and Path(vo).exists():  # la voz, junto al video (mismo nombre)
            shutil.copyfile(vo, media / f"{base}.mp3")
        kf = p.get("keyframe_path")
        if kf and Path(kf).exists():  # el keyframe, en frames/
            shutil.copyfile(kf, frames / f"{base}.png")

    if spec.music and Path(spec.music).exists():
        shutil.copyfile(spec.music, media / f"music{Path(spec.music).suffix}")

    final = next(iter(run.dir.glob("final_*.mp4")), None)  # rough cut = el final del run
    if final is not None:
        shutil.copyfile(final, export_dir / "rough_cut.mp4")

    (export_dir / "subtitulos.srt").write_text(srt_from_timeline(planos), encoding="utf-8")
    guion = export_dir / "guion.md"
    guion.write_text(render_guion(spec, planos), encoding="utf-8")
    _maybe_docx(guion)  # best-effort: deja guion.docx si hay node + conversor (D-030)
    return export_dir
