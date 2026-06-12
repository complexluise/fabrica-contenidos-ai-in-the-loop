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

from .assemble import _has_audio, concat_clips, trim_to, trim_to_tail
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
from .prompt_compile import (
    compose_keyframe_prompt,
    compose_ref_map,
    compose_start_pose_prompt,
    compose_video_prompt,
)
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
from .strategies.dispatch import build_strategy, routing_gaps, select_rule
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
                  scene_prompt: str, duration_s: float, aspect: str, seed: int,
                  chain_from: str | None = None) -> dict:
    return {
        "keyframe_key": keyframe_key,  # encadena: cambiar keyframe invalida el video
        "strategy": strategy,          # cambiar de estrategia invalida el clip
        "providers": provider_sig,     # {nombre: modelo} del subconjunto -> robusto a cambios de modelo
        "prompt": scene_prompt,
        "duration_s": duration_s,
        "aspect_ratio": aspect,
        "seed": seed,
        # D-059: identidad del frame-inicio = la key del clip anterior. Cambiar un
        # plano upstream invalida este (cascada de la cinta pixel-real).
        "chain_from": chain_from,
    }


def effective_voice(scene, shot) -> str | None:
    """Voz efectiva del plano (D-065): plano > escena. Dos hablantes pueden convivir
    en una escena (plano/contraplano) con su propia voz cada uno. Pura."""
    return shot.voice_id or scene.voice_id


def plan_ribbon(spec: ProjectSpec) -> list[dict]:
    """Aplana (escena, plano) en la cinta ordenada del film (D-059/D-060).

    Los planos son parte de las escenas (heredan prompt base/clase/refs/voz) pero
    el film los recorre como secuencia única, CRUZANDO los límites de escena.
    `transition_in` = la transición del plano anterior (cómo se ENTRA a este):
    alimenta el prompt del start-still (cuánta libertad de reencuadre, D-060)."""
    out: list[dict] = []
    transition_in: str | None = None  # primer plano del film: sin transición previa
    for scene in spec.scenes:
        for idx, shot in enumerate(effective_shots(scene)):
            shot_id = scene.id if idx == 0 else f"{scene.id}.{idx + 1}"
            out.append({"scene": scene, "shot": shot, "idx": idx,
                        "shot_id": shot_id, "transition_in": transition_in})
            transition_in = shot.transition
    return out


async def ensure_boundary_stills(project, spec: ProjectSpec, cfg: Config, keyframer,
                                 keyframe_overrides: dict, dry: bool = False) -> list[dict]:
    """Fase A del animatic (D-060): asegura las DOS poses frontera de cada plano.

    - **Destino** (el keyframe): el ancla elegida por el humano en el plano 1 de la
      escena; los planos 2+ se encadenan editando el destino previo (D-048/A2).
    - **Start-still**: la pose de APERTURA, generada editando el destino del plano
      ANTERIOR del film (cruza escenas → continuidad de elementos, incluso en
      cortes). El primer plano del film deriva de su propio destino ("momentos
      antes"). Todo cacheado: el animatic es revisable y el re-run cuesta $0.

    `dry=True` (D-061): solo LECTURA — computa las keys y mira el cache, sin
    generar ni gastar; las poses ausentes quedan None. Lo usan el endpoint GET
    del animatic y el status (visibilidad sin costo).

    Devuelve, por entrada de la cinta: {destino, kf_key, start, start_key, cost}.
    """
    # D-063: poses ELEGIDAS por el humano entre variantes (pose_picks.yaml).
    # Mismo patrón que el ancla: la pose elegida entra con key "picked:<nombre>"
    # -> cambiarla invalida el clip aguas abajo (cascada de cache correcta).
    pose_picks: dict = {}
    picks_path = project.dir / "pose_picks.yaml"
    if picks_path.exists():
        pose_picks = yaml.safe_load(picks_path.read_text(encoding="utf-8")) or {}

    out: list[dict] = []
    prev_destino = None  # destino del plano anterior DEL FILM (fuente del start)
    prev_destino_key = None
    scene_prev_kf = None  # destino previo DE LA ESCENA (cadena D-048)
    scene_prev_key = None
    current_scene_id = None
    for entry in plan_ribbon(spec):
        scene, shot = entry["scene"], entry["shot"]
        idx, shot_id = entry["idx"], entry["shot_id"]
        if scene.id != current_scene_id:
            current_scene_id = scene.id
            scene_prev_kf, scene_prev_key = None, None
            scene_anchor, scene_anchor_key = None, None  # D-064: el ancla de ESTA escena
        boundary = await _shot_boundaries(
            project=project, cfg=cfg, keyframer=keyframer, scene=scene, shot=shot,
            shot_id=shot_id, idx=idx, transition_in=entry["transition_in"],
            keyframe_overrides=keyframe_overrides, pose_picks=pose_picks,
            prev_destino=prev_destino, prev_destino_key=prev_destino_key,
            scene_prev_kf=scene_prev_kf, scene_prev_key=scene_prev_key,
            scene_anchor=scene_anchor, scene_anchor_key=scene_anchor_key,
            world=spec.world, dry=dry)
        out.append(boundary)
        # Las KEYS avanzan SIEMPRE (identidad pura/posicional de la cadena): un fallo
        # de generación deja el ARCHIVO en None pero no corre las keys aguas abajo —
        # si no, lo ya cacheado queda inalcanzable y los re-runs pagan de nuevo.
        prev_destino, prev_destino_key = boundary["destino"], boundary["kf_key"]
        scene_prev_kf, scene_prev_key = boundary["destino"], boundary["kf_key"]
        if idx == 0:  # D-064: el destino del plano 1 = el ancla de la escena
            scene_anchor, scene_anchor_key = boundary["destino"], boundary["kf_key"]
    return out


async def _shot_boundaries(*, project, cfg, keyframer, scene, shot, shot_id, idx,
                           transition_in, keyframe_overrides, pose_picks: dict | None = None,
                           prev_destino, prev_destino_key,
                           scene_prev_kf, scene_prev_key,
                           scene_anchor=None, scene_anchor_key=None,
                           world: str | None = None, dry: bool = False) -> dict:
    """Las dos poses frontera de UN plano (destino + start). Cacheadas."""
    from .project import _resolve_under
    pose_picks = pose_picks or {}
    refs_io = resolve_refs(project.dir, scene.character_refs)
    ref_sig = sorted(str(r) for r in scene.character_refs)
    cost = 0.0

    # --- destino (la lógica de keyframe de siempre, D-048) ---
    # Las KEYS se computan SIEMPRE (puras); la generación puede fallar y solo
    # afecta al ARCHIVO (None) — la identidad de la cadena no depende del runtime.
    kf_ext = compose_keyframe_prompt(shot)
    styled = build_styled_prompt(scene, cfg.style, kf_ext, world=world)
    chain_refs: list = []
    kf_inputs = _keyframe_inputs(styled, cfg, ref_sig)
    if idx > 0 and cfg.style.keyframe.ref_model:
        kf_inputs["chain_from"] = scene_prev_key  # identidad posicional, archivo aparte
        kf_inputs["anchor"] = scene_anchor_key    # D-064: cambiar el ancla regenera la escena
        if scene_prev_kf is not None:
            chain_refs = [scene_prev_kf]
        # D-064 (coherencia extrema): el ANCLA de la escena entra como referencia en
        # todas sus poses — el look elegido por el humano gobierna, no solo la cadena.
        if scene_anchor is not None and scene_anchor not in chain_refs:
            chain_refs = chain_refs + [scene_anchor]
    kf_key = cache_key("keyframe", kf_inputs)
    if idx == 0 and scene.id in keyframe_overrides:  # ancla elegida (D-022/D-025)
        destino = keyframe_overrides[scene.id]
        kf_key = f"picked:{destino.name}"
        logger.info("[%s] %s | destino directo (ancla): %s", shot_id, scene.class_, destino.name)
    else:
        destino = project.cache_lookup("keyframes", kf_key, ".png")
        if destino is None and not dry:
            try:
                logger.info("[%s] %s | generando destino%s...", shot_id, scene.class_,
                            " (encadenado)" if chain_refs else "")
                refs_for_gen = (chain_refs + refs_io) if chain_refs else refs_io
                ref_map = compose_ref_map(
                    source_label="this scene of the film" if chain_refs else None,
                    characters=list(scene.characters)) if refs_for_gen else None
                tmp = await keyframer.generate(
                    scene, ref_images=refs_for_gen, framing=kf_ext,
                    world=world, ref_map=ref_map)
                destino = project.cache_store("keyframes", kf_key, tmp, ".png")
                cost += cfg.style.keyframe.cost_per_image
            except Exception as exc:  # noqa: BLE001 — el fallo no corre la cadena
                logger.error("[%s] FALLO generando destino: %s", shot_id, exc)
                destino = None
    picked = pose_picks.get(f"{shot_id}/destino")
    if picked:  # D-063: variante elegida por el humano -> manda, con key propia
        p = _resolve_under(project.dir, picked)
        if p.exists():
            destino, kf_key = p, f"picked:{p.name}"

    # --- start-still: la pose de apertura, derivada del destino anterior ---
    # La KEY de la cadena sigue al destino previo aunque su archivo falte:
    # dry, render y re-runs deben computar EXACTAMENTE las mismas keys.
    if prev_destino_key is not None:
        source, source_key = prev_destino, prev_destino_key
    else:
        source, source_key = destino, kf_key  # primer plano: "momentos antes" del propio destino
    # D-064: el ancla de la escena también gobierna la APERTURA (para el plano 1,
    # el ancla es su propio destino). Coherencia extrema: el look elegido manda.
    anchor, anchor_key = (scene_anchor, scene_anchor_key) if idx > 0 else (destino, kf_key)
    start_ext = compose_start_pose_prompt(shot, transition_in)
    start_styled = build_styled_prompt(scene, cfg.style, start_ext, world=world)
    start_inputs = _keyframe_inputs(start_styled, cfg, ref_sig)
    start_inputs["role"] = "start_pose"        # namespace: no colisiona con destinos
    start_inputs["chain_from"] = source_key    # cambiar el destino previo invalida este
    start_inputs["anchor"] = anchor_key        # D-064: cambiar el ancla regenera la apertura
    start_key = cache_key("keyframe", start_inputs)
    start = project.cache_lookup("keyframes", start_key, ".png")
    if start is None and not dry and source is not None:
        try:
            logger.info("[%s] generando pose de apertura (animatic)...", shot_id)
            start_refs = [source]
            src_label = "the previous moment of this film"
            if anchor is not None and anchor != source:
                start_refs.append(anchor)
                src_label += "; image 2 = the look of THIS scene (continue it)"
            ref_map = compose_ref_map(source_label=src_label,
                                      characters=list(scene.characters))
            tmp = await keyframer.generate(scene, ref_images=start_refs + refs_io,
                                           framing=start_ext, world=world, ref_map=ref_map)
            start = project.cache_store("keyframes", start_key, tmp, ".png")
            cost += cfg.style.keyframe.cost_per_image
        except Exception as exc:  # noqa: BLE001 — el fallo no corre la cadena
            logger.error("[%s] FALLO generando pose de apertura: %s", shot_id, exc)
            start = None
    picked = pose_picks.get(f"{shot_id}/start")
    if picked:  # D-063: variante elegida -> manda, con key propia (cascada correcta)
        p = _resolve_under(project.dir, picked)
        if p.exists():
            start, start_key = p, f"picked:{p.name}"

    return {"destino": destino, "kf_key": kf_key, "start": start,
            "start_key": start_key, "cost": cost}


async def _render_shot(*, project, spec, cfg, run, gate, tts, mm,
                       scene, shot, shot_id, refs,
                       rule, subset, strategy, provider_sig,
                       keyframe, kf_key, stills_cost=0.0,
                       start_frame=None, chain_key=None):
    """Renderiza UN plano (D-028): video -> recorte -> sfx -> caption -> vo.

    D-060 (animatic): las poses frontera (destino + start) llegan YA generadas
    por `ensure_boundary_stills` (Fase A) → este paso es paralelizable. El video
    INTERPOLA `start_frame` → `keyframe` (el destino, donde aterriza); el recorte
    conserva la COLA (el aterrizaje), no la cabeza. `chain_key` (la key del
    start-still) entra a la cache key del clip.
    Devuelve (clip_path, record, manifest_entry, audio_applied, keyframe, kf_key).
    """
    refs_io = resolve_refs(project.dir, refs)
    kf_ext = compose_keyframe_prompt(shot)  # para el manifest (framing legible)

    # Escena efectiva del plano: prompt + MOVIMIENTO del plano (D-048/A1), audio/seed del plano.
    video_ext = compose_video_prompt(shot)
    # D-067: el modelo de VIDEO recibe el MISMO contexto que las imágenes — el
    # template de estilo + la biblia del mundo (antes le llegaba el prompt crudo:
    # Kling nunca supo que esto era toy photography). El negative también viaja.
    eff_prompt = build_styled_prompt(scene, cfg.style, video_ext, world=spec.world)
    plano = scene.model_copy(update={
        "id": shot_id, "prompt": eff_prompt, "duration_s": shot.duration_s,
        "keyframe": keyframe, "seed": shot.seed, "start_frame": start_frame,
        "voiceover": shot.voiceover, "caption": shot.caption, "character_refs": refs_io,
        "voice_id": effective_voice(scene, shot),  # D-065: el plano manda sobre la escena
        "negative_prompt": cfg.style.negative_prompt or None,  # D-067
    })

    # --- L5 video (cacheado) ---
    vid_key = cache_key("video", _video_inputs(
        kf_key, rule.strategy, provider_sig, eff_prompt, shot.duration_s, spec.format,
        shot.seed, chain_from=chain_key))
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
    # D-060: los clips anclados a destino ATERRIZAN al final → se conserva la COLA
    # (recorte de cabeza). El A/B mostró que recortar la cola tiraba el aterrizaje.
    if start_frame is not None:
        clip_path = trim_to_tail(result.video_path, run.dir / "_trim" / f"{shot_id}.mp4",
                                 shot.duration_s)
    else:
        clip_path = trim_to(result.video_path, run.dir / "_trim" / f"{shot_id}.mp4",
                            shot.duration_s)

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
        except Exception as exc:  # best-effort, pero VISIBLE (D-066): nada de fallos mudos
            logger.warning("[%s] sin audio diegético (%s): %s", shot_id, type(exc).__name__, exc)

    # --- L7 caption del plano (best-effort) ---
    cap = effective_caption(plano)
    if cap:
        try:
            clip_path = burn_lower_third(clip_path, run.dir / "captioned" / f"{shot_id}.mp4",
                                         cap, fontfile=default_font())
        except Exception as exc:
            logger.warning("[%s] sin caption (%s): %s", shot_id, type(exc).__name__, exc)

    # --- L7 voz en off del plano (best-effort, cacheada) ---
    vo_applied = False
    vo_file = None  # path del .mp3 de la voz (para el export, D-029)
    tts_cost = 0.0
    if plano.voiceover and tts is not None:
        try:
            voice_id = resolve_voice(plano, spec, default=cfg.voice.default_voice)
            vo_key = cache_key("voiceover", vo_inputs(plano.voiceover, voice_id, tts.model))
            vo_file = project.cache_lookup("voiceover", vo_key, ".mp3")
            if vo_file is None:
                scratch = run.dir / "_vo" / f"{shot_id}.mp3"
                await tts.synthesize(plano.voiceover, voice_id, scratch)
                vo_file = project.cache_store("voiceover", vo_key, scratch, ".mp3")
                tts_cost = round(getattr(tts, "cost_per_char", 0.0) * len(plano.voiceover), 6)
            clip_path = mux_voiceover(clip_path, vo_file, run.dir / "voiced" / f"{shot_id}.mp4")
            vo_applied = True
        except Exception as exc:
            logger.warning("[%s] sin voz en off (%s): %s", shot_id, type(exc).__name__, exc)

    record = SceneRecord(
        run_id=run.run_id, scene_id=shot_id, provider=result.provider,
        strategy=rule.strategy, scene_class=scene.class_,
        cost_usd=result.cost_usd, latency_s=result.latency_s,
        attempt=result.raw_meta.get("attempts", 1),
        passed=result.raw_meta.get("gate_passed", True),
        cached=cached, keyframe_key=kf_key, video_key=vid_key,
        audio_provider=audio_provider, audio_cost_usd=audio_cost,
        keyframe_cost_usd=stills_cost, tts_cost_usd=tts_cost)
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
    return (clip_path, record, manifest_entry, (vo_applied or diegetic_applied),
            keyframe, kf_key)


async def run_project(project: Project, spec: ProjectSpec, cfg: Config,
                      keyframe_overrides: dict | None = None,
                      concurrency: int = 1):
    """Ejecuta el proyecto. Devuelve (run, final_path, totals).

    `keyframe_overrides`: {scene_id: Path} con keyframes ya elegidos por el humano
    (modo interactivo D-022); si se da, no se genera/cachea el keyframe de esa escena.
    `concurrency`: escenas en vuelo simultaneo (D-039). Default 1 = serial.
    """
    keyframe_overrides = keyframe_overrides or {}
    # D-057: guard temprano de routing. Antes de construir providers o gastar, exigir
    # que cada escena tenga al menos un provider elegible para sus capabilities. Cierra
    # la simetría de "fallar temprano y claro" (D-055 selecciones, D-056 casting). El
    # caso típico: needs_audio:true sin provider de audio -> el router lanzaría a mitad
    # del run; acá se nombra antes de generar nada.
    gaps = routing_gaps(spec, cfg.routing, cfg.providers)
    if gaps:
        detail = "; ".join(f"{g['scene']} (falta: {', '.join(g['missing'])})" for g in gaps)
        raise RuntimeError(
            f"Estas escenas no tienen ningún provider elegible en el perfil activo: {detail}. "
            "Quita el requisito que no se puede cumplir (p.ej. needs_audio/needs_lipsync) "
            "o cambia a un perfil con un provider que lo soporte."
        )
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
        # D-058: el motor de voz lo elige el backend configurado (cfg.voice), no la
        # mera presencia de key. select_tts_backend degrada al motor disponible si
        # falta la credencial del pedido (voz best-effort, nunca bloquea el render).
        from .audio import select_tts_backend
        engine = select_tts_backend(cfg.voice.backend,
                                    has_elevenlabs=bool(settings.elevenlabs_api_key),
                                    has_fal=bool(settings.fal_key))
        if engine == "elevenlabs":
            tts = ElevenLabsTTS(settings.elevenlabs_api_key, model=cfg.voice.model or DEFAULT_VOICE_MODEL)
        elif engine == "kokoro":
            from .providers.fal_tts import FalTTS
            tts = FalTTS(settings.fal_key, model=cfg.voice.model)
        if engine and engine != cfg.voice.backend:
            logger.warning("TTS: '%s' pedido sin credencial; se usa '%s' (voz best-effort).",
                           cfg.voice.backend, engine)
        elif engine:
            logger.info("TTS: %s (backend de voz '%s')", engine, cfg.voice.backend)
        else:
            logger.warning("TTS: sin credenciales (ELEVENLABS/FAL); el video saldrá sin voz.")

    # Audio diegético (Sprint 6.9, D-034): SFX + ambiente vía MMAudio (fal). Solo
    # si algún plano trae un cue y hay FAL_KEY. Best-effort.
    any_cue = any(effective_audio_cue(s, sh) for s in spec.scenes for sh in effective_shots(s))
    mm = None
    audio_cfg = cfg.audio.get("mmaudio")  # modelo+costo desde config (D-034)
    if any_cue and audio_cfg is not None:
        fal_key_env = get_settings().fal_key
        if fal_key_env:
            mm = MMAudioV2(fal_key_env, audio_cfg)

    # --- D-060: animatic de poses frontera + interpolación EN PARALELO ----------
    # Fase A (secuencial, barata): las DOS poses de cada plano (destino + start)
    # quedan generadas/cacheadas — el esqueleto del film en stills curables.
    # Fase B (paralela, cara): cada clip interpola start→destino; los clips son
    # independientes entre sí → vuelve la concurrencia por plano (D-039).

    # Contexto por escena (clasificación, refs, regla), calculado una sola vez.
    scene_ctx: dict[str, tuple] = {}
    for scene in spec.scenes:
        scene.class_ = scene.class_ or classify(scene)
        refs = character_refs(scene, spec.characters)
        scene.character_refs = refs
        rule = select_rule(scene.class_, cfg.routing)
        subset = [providers_by_name[n] for n in rule.providers if n in providers_by_name]
        strategy = build_strategy(rule.strategy)
        provider_sig = {p.name: getattr(p, "model", p.name) for p in subset}
        scene_ctx[scene.id] = (refs, rule, subset, strategy, provider_sig)
        shots = effective_shots(scene)
        if len(shots) > 1:
            logger.info("[%s] %s | %d planos", scene.id, scene.class_, len(shots))

    ribbon = plan_ribbon(spec)
    boundaries = await ensure_boundary_stills(project, spec, cfg, keyframer,
                                              keyframe_overrides)

    sem = asyncio.Semaphore(concurrency)

    async def _one(entry: dict, b: dict | None):
        """Un plano de la Fase B. Devuelve la tupla del plano o None si falló."""
        scene, shot, shot_id = entry["scene"], entry["shot"], entry["shot_id"]
        if b is None or b["destino"] is None:  # sin destino no hay clip (la apertura es opcional)
            telemetry.record_failure(shot_id, "destino (animatic) no disponible")
            return None
        refs, rule, subset, strategy, provider_sig = scene_ctx[scene.id]
        async with sem:
            try:  # robustez: un plano que falla no aborta el run
                return await _render_shot(
                    project=project, spec=spec, cfg=cfg, run=run, gate=gate,
                    tts=tts, mm=mm, scene=scene, shot=shot, shot_id=shot_id,
                    refs=refs, rule=rule, subset=subset, strategy=strategy,
                    provider_sig=provider_sig, keyframe=b["destino"],
                    kf_key=b["kf_key"], stills_cost=b["cost"],
                    start_frame=b["start"], chain_key=b["start_key"])
            except Exception as exc:  # noqa: BLE001 — registra y sigue
                telemetry.record_failure(shot_id, str(exc))
                logger.error("[%s] FALLO: %s", shot_id, exc)
                logger.debug("[%s] traceback", shot_id, exc_info=True)
                return None

    # gather preserva el orden de las corutinas -> clips en orden de la cinta.
    results = await asyncio.gather(*(_one(e, b) for e, b in zip(ribbon, boundaries)))

    manifest_scenes: list[dict] = []
    clips: list = []
    audio_applied = False
    for res in results:
        if res is None:
            continue
        clip_path, record, mentry, audio, _kf, _key = res
        clips.append(clip_path)
        telemetry.record(record)
        manifest_scenes.append(mentry)
        audio_applied = audio_applied or audio

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
