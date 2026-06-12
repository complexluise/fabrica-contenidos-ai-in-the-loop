"""Helpers compartidos por las estrategias (L5)."""

from __future__ import annotations

from ..contracts import GenRequest, Scene


def eligible_providers(scene: Scene, providers: list) -> list:
    """Providers que cumplen las capabilities exigidas por la escena, en orden."""
    required = scene.requirements.required_capabilities()
    return [p for p in providers if p.supports(required)]


def scene_to_request(scene: Scene) -> GenRequest:
    """Escena/plano -> request del provider.

    D-070 (corrige D-059): si el plano trae `start_frame` (apertura de un plano
    `lands`), el clip INTERPOLA start→end — y el runner garantiza que el
    provider tenga capability `end_frame` (el end-frame REAL: `tail_image_url`
    de Kling PRO; los demás lo ignoraban en silencio). Sin apertura, el destino
    elegido entra como `init_image` (cámara-actúa).
    D-071/D-072: el formato del spec y el cfg_scale del plano viajan también."""
    extras = dict(
        negative_prompt=scene.negative_prompt,
        cfg_scale=scene.cfg_scale,
        seed=scene.seed,
    )
    if scene.aspect:
        extras["aspect_ratio"] = scene.aspect
    if scene.start_frame is not None:
        return GenRequest(
            prompt=scene.prompt,
            duration_s=scene.duration_s,
            init_image=scene.start_frame,
            end_image=scene.keyframe,
            **extras,
        )
    return GenRequest(
        prompt=scene.prompt,
        duration_s=scene.duration_s,
        init_image=scene.keyframe,
        **extras,
    )
