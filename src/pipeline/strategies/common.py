"""Helpers compartidos por las estrategias (L5)."""

from __future__ import annotations

from ..contracts import GenRequest, ShotJob


def eligible_providers(job: ShotJob, providers: list) -> list:
    """Providers que cumplen las capabilities exigidas por el plano, en orden."""
    required = job.requirements.required_capabilities()
    return [p for p in providers if p.supports(required)]


def job_to_request(job: ShotJob) -> GenRequest:
    """ShotJob -> request del provider (D-075).

    D-070 (corrige D-059): si el plano trae `start_frame` (apertura de un plano
    `lands`), el clip INTERPOLA start→end — y el runner garantiza que el
    provider tenga capability `end_frame` (el end-frame REAL: `tail_image_url`
    de Kling PRO; los demás lo ignoraban en silencio). Sin apertura, el destino
    elegido entra como `init_image` (cámara-actúa).
    D-071/D-072: el formato del spec y el cfg_scale del plano viajan también."""
    extras = dict(
        negative_prompt=job.negative_prompt,
        cfg_scale=job.cfg_scale,
        seed=job.seed,
    )
    if job.aspect:
        extras["aspect_ratio"] = job.aspect
    if job.start_frame is not None:
        return GenRequest(
            prompt=job.prompt,
            duration_s=job.duration_s,
            init_image=job.start_frame,
            end_image=job.keyframe,
            **extras,
        )
    return GenRequest(
        prompt=job.prompt,
        duration_s=job.duration_s,
        init_image=job.keyframe,
        **extras,
    )
