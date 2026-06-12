"""Generacion de musica de fondo via fal.ai (stable-audio).

Sin deps extras: usa fal_client (ya en core) + httpx para descargar el audio.
El resultado es un WAV que ffmpeg mezcla en concat_clips igual que un MP3.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

FAL_MUSIC_MODEL = "fal-ai/stable-audio"
logger = logging.getLogger(__name__)


async def generate_music_fal(
    prompt: str,
    duration_s: float,
    out_path: Path,
    fal_key: str,
    steps: int = 100,
) -> Path:
    """Genera musica con stable-audio (fal) y la guarda en out_path (.wav)."""
    import fal_client

    import asyncio

    client = fal_client.AsyncClient(key=fal_key)
    logger.info("Generando musica: %.0fs | %s", duration_s, prompt[:80])
    # Timeout duro (D-066): una cola trabada no debe colgar el flujo entero.
    result = await asyncio.wait_for(
        client.subscribe(
            FAL_MUSIC_MODEL,
            arguments={
                "prompt": prompt,
                # Schema real de fal-ai/stable-audio (verificado 2026-06-12):
                # seconds_total es INTEGER. Mandar float es apostar a la coercion.
                "seconds_total": int(round(min(float(duration_s), 190.0))),
                "steps": steps,
            },
        ),
        timeout=300,
    )
    audio_url = _extract_audio_url(result)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0) as http:
        r = await http.get(audio_url)
        r.raise_for_status()
        out_path.write_bytes(r.content)
    logger.info("Musica generada: %s (%d bytes)", out_path.name, out_path.stat().st_size)
    return out_path


def _extract_audio_url(result: dict) -> str:
    """stable-audio devuelve {'audio_file': {'url': '...'}} o variantes."""
    af = result.get("audio_file") or result.get("output")
    if isinstance(af, dict):
        url = af.get("url")
    elif isinstance(af, str):
        url = af
    else:
        url = None
    if not url:
        raise RuntimeError(f"Respuesta de fal sin audio utilizable: {result}")
    return url
