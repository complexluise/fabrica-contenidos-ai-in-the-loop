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
        out_path = await self._download(url)
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
            # D-070: el end-frame SOLO existe en endpoints con capability
            # `end_frame` (Kling 2.1 PRO: tail_image_url). fal ignora en
            # silencio los parámetros desconocidos — mandárselo a un modelo
            # incapaz es pagar i2v de deriva libre creyendo que interpola
            # (nos pasó: D-059/D-060 nunca se ejecutó). Acá se corta en seco.
            if "end_frame" in self.capabilities:
                end_url = await client.upload_file(str(req.end_image))
            else:
                import logging
                logging.getLogger(__name__).warning(
                    "%s no soporta end-frame; se ignora end_image (i2v libre). "
                    "Usa un provider con capability end_frame (p.ej. kling_pro).",
                    self.name)
        arguments = video_arguments(req.prompt, seed=req.seed,
                                    init_url=init_url, end_url=end_url,
                                    negative=req.negative_prompt,
                                    aspect=req.aspect_ratio,
                                    cfg_scale=req.cfg_scale)

        result = await asyncio.wait_for(
            client.subscribe(self.model, arguments=arguments),
            timeout=360,  # 6 min — video generation puede tardar en cola
        )
        return _extract_video_url(result)

    async def _download(self, url: str) -> Path:
        # D-076: scratch con uuid (hash() esta salteado por proceso — el nombre no
        # era determinista). El runner copia el clip a la cache del proyecto y
        # BORRA este crudo; out/clips ya no crece para siempre.
        import uuid

        out_dir = Path("out/clips")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.name}_{uuid.uuid4().hex[:8]}.mp4"
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


def video_arguments(prompt: str, seed: int | None = None,
                    init_url: str | None = None, end_url: str | None = None,
                    negative: str | None = None, aspect: str | None = None,
                    cfg_scale: float | None = None) -> dict:
    """Argumentos del job de video para fal (pura, testeable).

    `tail_image_url` (D-070, corrige D-059): el nombre REAL del end-frame en
    Kling 2.1 PRO. `end_image_url` no existe en ningún endpoint 2.1 y fal lo
    ignoraba en silencio — la interpolación nunca llegó al servidor.
    `aspect_ratio` (D-071): seedance lo honra; kling lo ignora (deriva el
    aspecto del init image, que ahora también viene en formato).
    `cfg_scale` (D-072): adherencia al prompt; None deja el default del modelo."""
    args: dict = {"prompt": prompt}
    if init_url:
        args["image_url"] = init_url
    if end_url:
        args["tail_image_url"] = end_url
    if negative:  # D-067: el video también merece saber qué NO queremos
        args["negative_prompt"] = negative
    if aspect:
        args["aspect_ratio"] = aspect
    if cfg_scale is not None:
        args["cfg_scale"] = cfg_scale
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
