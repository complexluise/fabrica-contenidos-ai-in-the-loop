"""L4 - Adapter Kling (image-to-video) via fal.ai.

Usa el cliente oficial fal_client (maneja submit+poll de la cola de fal). El
keyframe local se sube a fal con upload_file para obtener una URL (i2v necesita
URL, no path). La llamada esta aislada en `_submit_fal` para mockearla en tests.
Necesita FAL_KEY (via pipeline.settings) para el smoke run real.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from ..config import ProviderConfig
from ..contracts import GenRequest
from ..settings import get_settings
from .base import BaseProvider


class FalProvider(BaseProvider):
    """Provider generico sobre fal. El modelo concreto viene de la config."""

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self.model = cfg.model

    async def _call(self, req: GenRequest):
        url = await self._submit_fal(req)
        out_path = await self._download(url, req)
        return out_path, {"backend": "fal", "model": self.model, "remote_url": url}

    async def _submit_fal(self, req: GenRequest) -> str:
        """Envia el job a fal y devuelve la URL del video. Mockeable en tests."""
        import asyncio
        import fal_client

        key = get_settings().require("fal_key", "generacion de video via fal.ai")
        client = fal_client.AsyncClient(key=key)

        init_url = None
        end_url = None
        if req.init_image is not None:
            # i2v necesita URL; subimos el frame local a fal.
            init_url = await client.upload_file(str(req.init_image))
        if req.end_image is not None:
            # D-059: frame final/destino -> Kling 2.1 interpola start→end.
            end_url = await client.upload_file(str(req.end_image))
        arguments = video_arguments(req.prompt, seed=req.seed,
                                    init_url=init_url, end_url=end_url)

        result = await asyncio.wait_for(
            client.subscribe(self.model, arguments=arguments),
            timeout=360,  # 6 min — video generation puede tardar en cola
        )
        return _extract_video_url(result)

    async def _download(self, url: str, req: GenRequest) -> Path:
        out_dir = Path("out/clips")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.name}_{abs(hash((url, req.prompt))) & 0xFFFFFF:06x}.mp4"
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


def video_arguments(prompt: str, seed: int | None = None,
                    init_url: str | None = None, end_url: str | None = None) -> dict:
    """Argumentos del job de video para fal (pura, testeable).

    `end_image_url` (D-059): Kling 2.1 interpola entre el frame inicial y el final
    -> la cinta pixel-real encadena clips y aterriza en el destino del plano."""
    args: dict = {"prompt": prompt}
    if init_url:
        args["image_url"] = init_url
    if end_url:
        args["end_image_url"] = end_url
    if seed is not None:
        args["seed"] = seed
    return args


def _extract_video_url(result: dict) -> str:
    """fal devuelve el video en formas distintas segun el modelo. Tolerante."""
    video = result.get("video") or result.get("output")
    if isinstance(video, dict):
        url = video.get("url")
    elif isinstance(video, str):
        url = video
    else:
        url = None
    if not url:
        raise RuntimeError(f"Respuesta de fal sin video utilizable: {result}")
    return url
