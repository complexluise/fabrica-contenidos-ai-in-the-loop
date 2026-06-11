"""L4 - Adapter Veo (Google) via google-genai.

Fallback de proto cuando fal.ai no tiene credito. Auth propia de Google
(GOOGLE_API_KEY). El video se descarga como bytes desde Google Files API
(no es una URL publica — requiere el cliente autenticado).

Validado contra veo-2.0-generate-001. Si el modelo cambia, actualizar
providers.yaml.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import ProviderConfig
from ..contracts import GenRequest
from ..settings import get_settings
from .base import BaseProvider

POLL_INTERVAL = 15   # segundos entre polls
TIMEOUT_S     = 600  # 10 min max


class GoogleVeoProvider(BaseProvider):
    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self.model = cfg.model

    async def _call(self, req: GenRequest):
        out_path = await asyncio.wait_for(
            self._generate(req),
            timeout=TIMEOUT_S,
        )
        return out_path, {"backend": "google", "model": self.model}

    async def _generate(self, req: GenRequest) -> Path:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Instala google-genai: uv add google-genai"
            ) from exc

        key = get_settings().require("google_api_key", "generacion de video con Veo")
        client = genai.Client(api_key=key)

        config = types.GenerateVideosConfig(
            aspect_ratio=req.aspect_ratio or "9:16",
            number_of_videos=1,
            duration_seconds=min(int(req.duration_s or 5), 8),
        )
        kwargs: dict = {"model": self.model, "prompt": req.prompt, "config": config}
        if req.init_image is not None:
            kwargs["image"] = types.Image.from_file(location=str(req.init_image))

        # submit — sincrono (SDK no ofrece async aqui); rapido, solo encola
        operation = await asyncio.to_thread(
            client.models.generate_videos, **kwargs
        )

        # poll — asyncio.sleep para no bloquear el event loop
        elapsed = 0
        while not operation.done:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            operation = await asyncio.to_thread(client.operations.get, operation)

        videos = operation.response.generated_videos
        if not videos:
            raise RuntimeError("Veo: la operacion termino sin videos")

        video = videos[0].video

        # Descargar — Google Files devuelve bytes autenticados, no URL publica
        video_bytes = await asyncio.to_thread(client.files.download, file=video)

        out_dir = Path("out/clips")
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = abs(hash(req.prompt)) & 0xFFFFFF
        out_path = out_dir / f"veo_{slug:06x}.mp4"
        out_path.write_bytes(video_bytes)
        return out_path
