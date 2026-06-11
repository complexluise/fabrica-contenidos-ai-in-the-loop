"""Helpers compartidos por las estrategias (L5)."""

from __future__ import annotations

from ..contracts import GenRequest, Scene


def eligible_providers(scene: Scene, providers: list) -> list:
    """Providers que cumplen las capabilities exigidas por la escena, en orden."""
    required = scene.requirements.required_capabilities()
    return [p for p in providers if p.supports(required)]


def scene_to_request(scene: Scene) -> GenRequest:
    """Escena/plano -> request del provider.

    D-059 (cinta pixel-real): si el plano trae `start_frame` (el último frame real
    del clip anterior), el clip INTERPOLA start→end y el keyframe elegido es el
    DESTINO (`end_image`), no el frame-0. Sin cadena (corte o primer plano), el
    keyframe entra como `init_image` (comportamiento clásico)."""
    if scene.start_frame is not None:
        return GenRequest(
            prompt=scene.prompt,
            duration_s=scene.duration_s,
            init_image=scene.start_frame,
            end_image=scene.keyframe,
            seed=scene.seed,
        )
    return GenRequest(
        prompt=scene.prompt,
        duration_s=scene.duration_s,
        init_image=scene.keyframe,
        seed=scene.seed,
    )
