"""L4 - Adapter MMAudio V2 (video-to-audio) vía fal.ai (D-034).

Toma un clip **ya generado** (mudo) + un cue de texto (SFX + ambiente) y, leyendo
los frames, devuelve el mismo clip con **audio sincronizado** muxeado. Así el
diseño sonoro no se descuadra con la imagen y cuesta centavos ($0.001/s), sin
salir de fal ([D-002]). Aislado en `_submit_fal` para mockearlo; se valida con
smoke real (es I/O de red).

Doc: https://fal.ai/models/fal-ai/mmaudio-v2
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .fal_kling import _extract_video_url

_MODEL = "fal-ai/mmaudio-v2"


class MMAudioV2:
    """Genera audio diegético (sfx + ambiente) para un clip vía MMAudio en fal."""

    name = "mmaudio"

    def __init__(self, api_key: str, model: str = _MODEL, timeout: float = 600.0):
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def add_audio(self, clip: Path, cue: str, out_path: Path, seed: int = 0) -> Path:
        """Agrega audio sincronizado a `clip` según `cue` y guarda el video en `out_path`."""
        url = await self._submit_fal(clip, cue, seed)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path

    async def _submit_fal(self, clip: Path, cue: str, seed: int) -> str:
        """Sube el clip a fal, corre MMAudio y devuelve la URL del video con audio.

        No fija `duration`: MMAudio usa la longitud del clip (ya recortado al plano).
        """
        import fal_client

        client = fal_client.AsyncClient(key=self._api_key)
        video_url = await client.upload_file(str(clip))
        arguments = {"video_url": video_url, "prompt": cue, "seed": seed}
        result = await client.subscribe(self.model, arguments=arguments)
        return _extract_video_url(result)
