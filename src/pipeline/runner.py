"""Orquestador de proyecto con caché content-addressed (SPEC §7).

Por cada escena: keyframe y video se llavean por hash de sus inputs y se buscan
en el cache del proyecto. Si hay hit -> no se llama a la API (costo 0). Si hay
miss -> se genera y se guarda bajo su key. El run queda como manifiesto + report
+ render final dentro de projects/<slug>/runs/<run_id>/.

Aquí viven las llamadas reales a API (no unit-test; se valida con smoke run).
"""

from __future__ import annotations

import asyncio
import logging

import yaml

from .assemble import _has_audio, concat_clips, trim_to
from .audio import (
    DEFAULT_VOICE_MODEL,
    effective_audio_cue,
    effective_caption,
    mux_voiceover,
    resolve_voice,
    sfx_inputs,
    vo_inputs,
)
from .classifier import classify
from .config import Config
from .contracts import GenResult
from .deliver import reframe
from .gate import FusedGate
from .keyframe import KeyframeGenerator, build_styled_prompt
from .prompt_compile import compose_keyframe_prompt, compose_video_prompt
from .post import burn_lower_third, default_font
from .project import (
    Project,
    ProjectSpec,
    cache_key,
    character_refs,
    effective_shots,
    resolve_refs,
)
from .providers.base import build_provider
from .providers.elevenlabs_tts import ElevenLabsTTS
from .providers.mmaudio import MMAudioV2
from .settings import get_settings
from .logging_setup import add_run_logfile, remove_handler
from .strategies.dispatch import build_strategy, select_rule
from .telemetry import SceneRecord, Telemetry

logger = logging.getLogger(__name__)


def _keyframe_inputs(styled_prompt: str, cfg: Config, ref_sig: list[str]) -> dict:
    kf = cfg.style.keyframe
    return {
        "prompt": styled_prompt,
        "negative": cfg.style.negative_prompt,
        "model": kf.model,
        "lora": kf.lora,
        "strength": kf.strength,
        # Identidad: cambiar referencias o el modelo de edición invalida el keyframe.
        "ref_model": kf.ref_model if ref_sig else None,
        "character_refs": ref_sig,
    }


def _video_inputs(keyframe_key: str, strategy: str, provider_sig: dict,
                  scene_prompt: str, duration_s: float, aspect: str, seed: int) -> dict:
    return {
        "keyframe_key": keyframe_key,  # encadena: cambiar keyframe invalida el video
        "strategy": strategy,          # cambiar de estrategia invalida el clip
        "providers": provider_sig,     # {nombre: modelo} del subconjunto -> robusto a cambios de modelo
        "prompt": scene_prompt,
        "duration_s": duration_s,
        "aspect_ratio": aspect,
        "seed": seed,
    }


async def _render_shot(*, project, spec, cfg, run, keyframer, gate, tts, mm,
                       scene, shot, shot_id, idx, refs, ref_sig,
                       rule, subset, strategy, provider_sig, keyframe_overrides,
                       prev_keyframe=None, prev_kf_key=None):
    """Renderiza UN plano (D-028): keyframe -> video -> recorte -> sfx -> caption -> vo.

    Plano 1 (idx 0) puede traer el keyframe **elegido** por el humano (el ancla de
    la escena). Los planos 2+ se **encadenan** desde el keyframe del plano previo
    (i2i) para coherencia visual (D-048/A2). Keyframe = imagen FIJA (sin
    movimiento); el movimiento va al prompt de VIDEO (D-048/A1).
    Devuelve (clip_path, SceneRecord, manifest_entry, audio_applied, keyframe, kf_key).
    """
    # Refs project-relative -> absolutas SOLO para I/O (keyframer + gate). El cache
    # key sigue con `ref_sig` (relativo, estable). Mismo criterio que studio (D-034).
    refs_io = resolve_refs(project.dir, refs)

    # --- L3 keyframe (cacheado, con identidad de personaje) ---
    # D-048/A1: el keyframe usa el prompt FIJO (action + camara fija + visual); el
    # movimiento (camera.move) va al video, no a la imagen.
    kf_ext = compose_keyframe_prompt(shot)
    styled = build_styled_prompt(scene, cfg.style, kf_ext)
    # D-048/A2: planos 2+ encadenan desde el keyframe previo (i2i). El plano previo
    # entra como ref extra al modelo de edicion; su key encadena el cache.
    chain_refs: list = []
    kf_inputs = _keyframe_inputs(styled, cfg, ref_sig)
    if idx > 0 and prev_keyframe is not None and cfg.style.keyframe.ref_model:
        chain_refs = [prev_keyframe]
        kf_inputs["chain_from"] = prev_kf_key  # cambiar el plano previo invalida este
    kf_key = cache_key("keyframe", kf_inputs)
    kf_cost = 0.0
    if idx == 0 and scene.id in keyframe_overrides:  # plano 1 = ancla elegida/inyectada (D-022/D-025)
        keyframe = keyframe_overrides[scene.id]
        kf_key = f"picked:{keyframe.name}"
        logger.info("[%s] %s | keyframe directo (ancla): %s", shot_id, scene.class_, keyframe.name)
    else:
        kf_hit = project.cache_lookup("keyframes", kf_key, ".png")
        if kf_hit is not None:
            keyframe = kf_hit
            logger.info("[%s] keyframe (cache hit): %s", shot_id, kf_hit.name)
        else:
            chained = " (encadenado)" if chain_refs else ""
            logger.info("[%s] %s | generando keyframe%s...", shot_id, scene.class_, chained)
            tmp = await keyframer.generate(
                scene, ref_images=(chain_refs + refs_io) if chain_refs else refs_io,
                framing=kf_ext)
            keyframe = project.cache_store("keyframes", kf_key, tmp, ".png")
            kf_cost = cfg.style.keyframe.cost_per_image
            logger.info("[%s] keyframe generado: %s ($%.4f)", shot_id, keyframe.name, kf_cost)

    # Escena efectiva del plano: prompt + MOVIMIENTO del plano (D-048/A1), audio/seed del plano.
    video_ext = compose_video_prompt(shot)
    eff_prompt = scene.prompt if not video_ext else f"{scene.prompt}, {video_ext}"
    plano = scene.model_copy(update={
        "id": shot_id, "prompt": eff_prompt, "duration_s": shot.duration_s,
        "keyframe": keyframe, "seed": shot.seed,
        "voiceover": shot.voiceover, "caption": shot.caption, "character_refs": refs_io,
    })

    # --- L5 video (cacheado) ---
    vid_key = cache_key("video", _video_inputs(
        kf_key, rule.strategy, provider_sig, eff_prompt, shot.duration_s, spec.format, shot.seed))
    vid_hit = project.cache_lookup("clips", vid_key, ".mp4")
    if vid_hit is not None:
        meta = project.sidecar_lookup("clips", vid_key) or {}
        result = GenResult(video_path=vid_hit, provider=meta.get("provider", "cache"),
                           cost_usd=0.0, latency_s=0.0,
                           raw_meta={"cached": True, "gate_passed": meta.get("gate_passed", True),
                                     "gate_scores": meta.get("gate_scores", {})})
        cached = True
        logger.info("[%s] video (cache hit): %s", shot_id, result.provider)
    else:
        logger.info("[%s] video: %s -> %s | generando...",
                    shot_id, rule.strategy, [p.name for p in subset])
        result = await strategy.run(plano, subset, gate)
        stored = project.cache_store("clips", vid_key, result.video_path, ".mp4")
        result.video_path = stored
        project.sidecar_store("clips", vid_key, {
            "provider": result.provider,
            "gate_passed": result.raw_meta.get("gate_passed", True),
            "gate_scores": result.raw_meta.get("gate_scores", {})})
        cached = False
        gate_str = "ok" if result.raw_meta.get("gate_passed", True) else "fail"
        logger.info("[%s] video listo: %s | $%.3f | %.1fs | gate=%s",
                    shot_id, result.provider, result.cost_usd, result.latency_s, gate_str)

    # --- recorte a la duración del plano (conservador: solo si el clip es más largo) ---
    clip_path = trim_to(result.video_path, run.dir / "_trim" / f"{shot_id}.mp4", shot.duration_s)

    # --- L7 audio diegético: SFX (acción) + ambiente (lugar) vía V2A (D-034) ---
    # Best-effort y cacheado. Si el clip YA trae audio (modelo nativo tipo Veo),
    # se respeta y se omite MMAudio (decisión por routing, AC5).
    cue = effective_audio_cue(scene, shot)
    diegetic_applied = False
    sfx_key = None
    audio_provider = ""
    audio_cost = 0.0
    if cue and mm is not None and not _has_audio(clip_path):
        try:
            sfx_key = cache_key("sfx", {"video_key": vid_key, **sfx_inputs(cue, mm.model, shot.seed)})
            hit = project.cache_lookup("sfx", sfx_key, ".mp4")
            if hit is not None:
                clip_path = hit
                logger.info("[%s] audio diegético (cache hit)", shot_id)
            else:
                logger.info("[%s] audio diegético: %s | generando (MMAudio)...", shot_id, cue)
                scratch = run.dir / "_sfx" / f"{shot_id}.mp4"
                await mm.add_audio(clip_path, cue, scratch, seed=shot.seed)
                clip_path = project.cache_store("sfx", sfx_key, scratch, ".mp4")
                audio_cost = round(mm.cost_per_second * shot.duration_s, 4)  # solo si se generó
            diegetic_applied = True
            audio_provider = mm.name
        except Exception:
            pass  # sin diegético antes que perder el plano

    # --- L7 caption del plano (best-effort) ---
    cap = effective_caption(plano)
    if cap:
        try:
            clip_path = burn_lower_third(clip_path, run.dir / "captioned" / f"{shot_id}.mp4",
                                         cap, fontfile=default_font())
        except Exception:
            pass  # sin caption antes que perder el plano

    # --- L7 voz en off del plano (best-effort, cacheada) ---
    vo_applied = False
    vo_file = None  # path del .mp3 de la voz (para el export, D-029)
    tts_cost = 0.0
    if plano.voiceover and tts is not None:
        try:
            voice_id = resolve_voice(plano, spec)
            vo_key = cache_key("voiceover", vo_inputs(plano.voiceover, voice_id, tts.model))
            vo_file = project.cache_lookup("voiceover", vo_key, ".mp3")
            if vo_file is None:
                scratch = run.dir / "_vo" / f"{shot_id}.mp3"
                await tts.synthesize(plano.voiceover, voice_id, scratch)
                vo_file = project.cache_store("voiceover", vo_key, scratch, ".mp3")
                tts_cost = round(getattr(tts, "cost_per_char", 0.0) * len(plano.voiceover), 6)
            clip_path = mux_voiceover(clip_path, vo_file, run.dir / "voiced" / f"{shot_id}.mp4")
            vo_applied = True
        except Exception:
            pass  # sin VO antes que perder el plano

    record = SceneRecord(
        run_id=run.run_id, scene_id=shot_id, provider=result.provider,
        strategy=rule.strategy, scene_class=scene.class_,
        cost_usd=result.cost_usd, latency_s=result.latency_s,
        attempt=result.raw_meta.get("attempts", 1),
        passed=result.raw_meta.get("gate_passed", True),
        cached=cached, keyframe_key=kf_key, video_key=vid_key,
        audio_provider=audio_provider, audio_cost_usd=audio_cost,
        keyframe_cost_usd=kf_cost, tts_cost_usd=tts_cost)
    manifest_entry = {
        "id": shot_id, "scene": scene.id, "beat": scene.beat, "class": scene.class_,
        "strategy": rule.strategy, "provider": result.provider,
        "keyframe_key": kf_key, "keyframe_path": str(keyframe),
        "video_key": vid_key, "cached": cached, "duration_s": shot.duration_s,
        "seed": shot.seed, "framing": kf_ext or shot.framing, "caption": cap,
        "intention": shot.intention or "",  # D-047: funcion dramatica al guion
        "motion": video_ext or "",  # D-048/A1: el movimiento que se le pidio al video
        "voiceover": plano.voiceover or "", "vo_path": str(vo_file) if vo_file else None,
        "sfx": shot.sfx or "", "ambience": scene.ambience or "", "sfx_key": sfx_key,
        "characters": scene.characters, "gate_scores": result.raw_meta.get("gate_scores", {})}
    return clip_path, record, manifest_entry, (vo_applied or diegetic_applied), keyframe, kf_key


async def run_project(project: Project, spec: ProjectSpec, cfg: Config,
                      keyframe_overrides: dict | None = None,
                      concurrency: int = 1):
    """Ejecuta el proyecto. Devuelve (run, final_path, totals).

    `keyframe_overrides`: {scene_id: Path} con keyframes ya elegidos por el humano
    (modo interactivo D-022); si se da, no se genera/cachea el keyframe de esa escena.
    `concurrency`: escenas en vuelo simultaneo (D-039). Default 1 = serial.
    """
    keyframe_overrides = keyframe_overrides or {}
    providers_by_name = {n: build_provider(p) for n, p in cfg.providers.items()}
    # D-052: gate deshabilitado si el perfil lo pide (lista vacía → permisivo).
    from .gate.fused import _build_default_signals
    if cfg.profile.gate.enabled:
        signals = _build_default_signals(vlm_model=cfg.profile.gate.vlm_model)
    else:
        signals = []
    gate = FusedGate(cfg.routing.thresholds, enforce=cfg.routing.enforce, signals=signals)

    run = project.new_run()
    run_log = add_run_logfile(run.dir / "run.log")  # detalle completo por corrida (L9)
    logger.info("run %s | %d escenas | estilo %s | formato %s | concurrencia %d",
                run.run_id, len(spec.scenes), spec.style, spec.format, concurrency)
    # D-053: backend del keyframe viene del storyboard backend activo.
    keyframer = KeyframeGenerator(cfg.style, out_dir=run.dir / "_scratch",
                                   backend=cfg.storyboard.keyframe.backend)
    telemetry = Telemetry(run.run_id, db_path=run.dir / "telemetry.sqlite")

    # Voz en off (Sprint 6): chequea scene.voiceover Y shot.voiceover (ambos válidos).
    any_vo = any(
        s.voiceover or any(sh.voiceover for sh in effective_shots(s))
        for s in spec.scenes
    )
    tts = None
    if any_vo:
        settings = get_settings()
        vo_key_env = settings.elevenlabs_api_key
        if vo_key_env:
            tts = ElevenLabsTTS(vo_key_env, model=DEFAULT_VOICE_MODEL)
            logger.info("TTS: ElevenLabs (%s)", DEFAULT_VOICE_MODEL)
        elif settings.fal_key:
            from .providers.fal_tts import FalTTS
            tts = FalTTS(settings.fal_key)
            logger.info("TTS: fal-ai/kokoro (fallback; sin ELEVENLABS_API_KEY)")

    # Audio diegético (Sprint 6.9, D-034): SFX + ambiente vía MMAudio (fal). Solo
    # si algún plano trae un cue y hay FAL_KEY. Best-effort.
    any_cue = any(effective_audio_cue(s, sh) for s in spec.scenes for sh in effective_shots(s))
    mm = None
    audio_cfg = cfg.audio.get("mmaudio")  # modelo+costo desde config (D-034)
    if any_cue and audio_cfg is not None:
        fal_key_env = get_settings().fal_key
        if fal_key_env:
            mm = MMAudioV2(fal_key_env, audio_cfg)

    # --- loop de escenas con semaforo de concurrencia (D-039) ----------------
    sem = asyncio.Semaphore(concurrency)

    async def _process_scene(scene):
        """Todos los planos de una escena, en serie. Devuelve (clips, records, manifests, audio)."""
        async with sem:
            scene.class_ = scene.class_ or classify(scene)
            refs = character_refs(scene, spec.characters)
            scene.character_refs = refs
            ref_sig = sorted(str(r) for r in refs)
            rule = select_rule(scene.class_, cfg.routing)
            subset = [providers_by_name[n] for n in rule.providers if n in providers_by_name]
            strategy = build_strategy(rule.strategy)
            provider_sig = {p.name: getattr(p, "model", p.name) for p in subset}

            shots = effective_shots(scene)  # D-028: planos reales o 1 implícito (compat)
            if len(shots) > 1:
                logger.info("[%s] %s | %d planos", scene.id, scene.class_, len(shots))

            s_clips, s_records, s_manifests, s_audio = [], [], [], False
            prev_keyframe = None  # D-048/A2: encadena los planos de ESTA escena
            prev_kf_key = None
            for idx, shot in enumerate(shots):
                shot_id = scene.id if idx == 0 else f"{scene.id}.{idx + 1}"
                try:  # robustez: un plano que falla no aborta el run
                    clip_path, record, mentry, audio, kf_path, kf_key = await _render_shot(
                        project=project, spec=spec, cfg=cfg, run=run, keyframer=keyframer,
                        gate=gate, tts=tts, mm=mm, scene=scene, shot=shot, shot_id=shot_id,
                        idx=idx, refs=refs, ref_sig=ref_sig, rule=rule, subset=subset,
                        strategy=strategy, provider_sig=provider_sig,
                        keyframe_overrides=keyframe_overrides,
                        prev_keyframe=prev_keyframe, prev_kf_key=prev_kf_key)
                    s_clips.append(clip_path)
                    s_records.append(record)
                    s_manifests.append(mentry)
                    s_audio = s_audio or audio
                    prev_keyframe, prev_kf_key = kf_path, kf_key  # encadena al siguiente plano
                except Exception as exc:  # noqa: BLE001 — robustez: registra y sigue
                    telemetry.record_failure(shot_id, str(exc))
                    logger.error("[%s] FALLO: %s", shot_id, exc)
                    logger.debug("[%s] traceback", shot_id, exc_info=True)
            return s_clips, s_records, s_manifests, s_audio

    # asyncio.gather preserva el orden de las corutinas -> clips en orden de escenas.
    scene_results = await asyncio.gather(
        *[_process_scene(s) for s in spec.scenes],
        return_exceptions=True,
    )

    manifest_scenes: list[dict] = []
    clips = []
    audio_applied = False
    for scene, result in zip(spec.scenes, scene_results):
        if isinstance(result, Exception):
            telemetry.record_failure(scene.id, str(result))
            logger.error("[%s] escena fallo: %s", scene.id, result)
        else:
            s_clips, s_records, s_manifests, s_audio = result
            clips.extend(s_clips)
            for r in s_records:
                telemetry.record(r)
            manifest_scenes.extend(s_manifests)
            audio_applied = audio_applied or s_audio

    if not clips:
        # El reporte se escribe aun en el peor caso: el mensaje promete failures
        # en run_report.json, así que el archivo TIENE que existir (D-054).
        telemetry.write_report(run.report_path)
        telemetry.close()
        logger.error("run %s | todas las escenas fallaron", run.run_id)
        remove_handler(run_log)
        raise RuntimeError("Todas las escenas fallaron; revisa run_report.json (failures).")

    try:
        music = spec.music if (spec.music and spec.music.exists()) else None
        # Con voz o audio diegético, la música baja para quedar por debajo (ducking, D-034).
        music_volume = 0.25 if audio_applied else 1.0
        stitched = concat_clips(clips, run.dir / "_stitched.mp4", music=music,
                                music_volume=music_volume)
        final = reframe(stitched, run.dir / f"final_{spec.format.replace(':', 'x')}.mp4", spec.format)
        _write_manifest(run, spec, cfg, manifest_scenes)
    finally:
        # Telemetría: cierre y reporte garantizados aunque el ensamblaje (ffmpeg)
        # reviente a mitad. Sin esto, un fallo en concat/reframe dejaba la DB
        # abierta y el run_report.json sin escribir (feedback Sprint 1 #10, D-054).
        telemetry.write_report(run.report_path)
        totals = telemetry.totals()
        telemetry.close()
        remove_handler(run_log)

    logger.info("run %s | OK | %d clips | $%.3f | cache %d/%d | %s",
                run.run_id, len(clips), totals["total_cost_usd"],
                totals["cache_hits"], totals["attempts"], final.name)
    return run, final, totals


def _write_manifest(run, spec: ProjectSpec, cfg: Config, scenes: list[dict]) -> None:
    manifest = {
        "run_id": run.run_id,
        "project": spec.slug,
        "style": spec.style,
        "format": spec.format,
        "providers": {n: p.model for n, p in cfg.providers.items()},
        "scenes": scenes,
    }
    run.manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
