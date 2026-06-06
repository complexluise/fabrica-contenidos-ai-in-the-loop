"""L3 - Keyframe stage: la capa que da el estilo (LEGO) y la consistencia.

En API-only el LoRA NO va en el modelo de video. Aqui se genera una imagen de
estilo con Flux+LoRA (via fal) que luego entra como init_image (image-to-video).
Cambiar el style YAML cambia el look sin tocar nada mas.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .config import StyleConfig
from .contracts import Scene
from .settings import get_settings


def build_styled_prompt(scene: Scene, style: StyleConfig, framing: str = "") -> str:
    """Inyecta el prompt de la escena (+ el framing del plano) en el template de estilo.

    `framing` EXTIENDE el prompt de la escena (D-028): el plano hereda el setting
    y suma su encuadre. Sin framing, el prompt efectivo es el de la escena (clave
    de caché estable hacia atrás).
    """
    base = scene.prompt if not framing else f"{scene.prompt}, {framing}"
    return style.prompt_template.format(scene_prompt=base).strip()


class KeyframeGenerator:
    """Genera el keyframe de estilo por escena. `_submit_fal` aislado para tests."""

    def __init__(self, style: StyleConfig, out_dir: Path = Path("out/keyframes")):
        self.style = style
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, scene: Scene, ref_images: list[Path] | None = None,
                       seed: int | None = None, framing: str = "") -> Path:
        prompt = build_styled_prompt(scene, self.style, framing)
        if ref_images and self.style.keyframe.ref_model:
            url = await self._submit_ref(prompt, ref_images, seed)  # propaga identidad
        else:
            url = await self._submit_fal(prompt, seed)
        return await self._download(url, self.out_dir / f"{scene.id}.png")

    async def generate_design(self, design_prompt: str, ref_images: list[Path],
                              seed: int | None = None) -> Path:
        """Casting/look-dev: combina imágenes de entrada (persona + LEGO) + prompt -> cara."""
        styled = self.style.prompt_template.format(scene_prompt=design_prompt).strip()
        if ref_images and self.style.keyframe.ref_model:
            url = await self._submit_ref(styled, ref_images, seed)
        else:
            url = await self._submit_fal(styled, seed)
        return await self._download(url, self.out_dir / f"cast_{seed}.png")

    async def _submit_ref(self, prompt: str, ref_images: list[Path], seed: int | None = None) -> str:
        """Genera el keyframe condicionado a imágenes de referencia (consistencia)."""
        import fal_client

        key = get_settings().require("fal_key", "keyframe con referencia de personaje")
        client = fal_client.AsyncClient(key=key)
        urls = [await client.upload_file(str(p)) for p in ref_images]
        arguments = {"prompt": prompt, "image_urls": urls}
        if seed is not None:
            arguments["seed"] = seed
        result = await client.subscribe(self.style.keyframe.ref_model, arguments=arguments)
        images = result.get("images") or []
        if not images:
            raise RuntimeError(f"Respuesta de fal (ref) sin imagen: {result}")
        return images[0]["url"]

    async def _submit_fal(self, prompt: str, seed: int | None = None) -> str:
        import fal_client

        key = get_settings().require("fal_key", "generacion de keyframes / capa de estilo")
        client = fal_client.AsyncClient(key=key)

        kf = self.style.keyframe
        arguments: dict = {"prompt": prompt}
        if seed is not None:
            arguments["seed"] = seed
        if self.style.negative_prompt:
            arguments["negative_prompt"] = self.style.negative_prompt
        # Aplica el LoRA solo si esta configurado (no el placeholder <...>).
        if kf.lora and not kf.lora.startswith("<"):
            arguments["loras"] = [{"path": kf.lora, "scale": kf.strength}]

        result = await client.subscribe(kf.model, arguments=arguments)
        images = result.get("images") or []
        if not images:
            raise RuntimeError(f"Respuesta de fal sin imagen: {result}")
        return images[0]["url"]

    async def _download(self, url: str, out_path: Path) -> Path:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path
