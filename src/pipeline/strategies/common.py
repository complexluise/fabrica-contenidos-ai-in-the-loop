"""Helpers compartidos por las estrategias (L5)."""

from __future__ import annotations

from ..contracts import GenRequest, Scene


def eligible_providers(scene: Scene, providers: list) -> list:
    """Providers que cumplen las capabilities exigidas por la escena, en orden."""
    required = scene.requirements.required_capabilities()
    return [p for p in providers if p.supports(required)]


def scene_to_request(scene: Scene) -> GenRequest:
    return GenRequest(
        prompt=scene.prompt,
        duration_s=scene.duration_s,
        init_image=scene.keyframe,
        seed=scene.seed,
    )
