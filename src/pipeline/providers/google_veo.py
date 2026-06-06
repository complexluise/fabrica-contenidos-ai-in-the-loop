"""L4 - Adapter directo de Veo 3.1 (Google) via google-genai.

Único modelo con audio+diálogo sincronizado nativo -> tier hero. Auth/billing
propios de Google (no fal). La llamada real está aislada en `_submit_veo` para
poder mockearla; requiere GOOGLE_API_KEY (via pipeline.settings) y el extra
google-genai. Pendiente de validar contra la API real en el primer smoke con key
(igual que pasó con el adapter de fal).
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from ..config import ProviderConfig
from ..contracts import GenRequest
from ..settings import get_settings
from .base import BaseProvider


class GoogleVeoProvider(BaseProvider):
    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self.model = cfg.model

    async def _call(self, req: GenRequest):
        url = await self._submit_veo(req)
        out_path = await self._download(url, req)
        return out_path, {"backend": "google", "model": self.model, "remote_url": url}

    async def _submit_veo(self, req: GenRequest) -> str:
        """Genera el video con Veo y devuelve la URL/archivo. Mockeable en tests."""
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Instala google-genai para usar Veo: uv add google-genai"
            ) from exc

        key = get_settings().require("google_api_key", "generación de video con Veo")
        client = genai.Client(api_key=key)

        config = types.GenerateVideosConfig(aspect_ratio=req.aspect_ratio)
        kwargs = {"model": self.model, "prompt": req.prompt, "config": config}
        if req.init_image is not None:
            kwargs["image"] = types.Image.from_file(location=str(req.init_image))

        operation = client.models.generate_videos(**kwargs)
        # Veo es asíncrono: poll hasta completar.
        while not operation.done:
            time.sleep(10)
            operation = client.operations.get(operation)

        video = operation.response.generated_videos[0].video
        return getattr(video, "uri", None) or getattr(video, "url", "")

    async def _download(self, url: str, req: GenRequest) -> Path:
        out_dir = Path("out/clips")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.name}_{abs(hash((url, req.prompt))) & 0xFFFFFF:06x}.mp4"
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path
