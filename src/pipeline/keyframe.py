"""L3 - Keyframe stage: la capa que da el estilo (LEGO) y la consistencia.

En API-only el LoRA NO va en el modelo de video. Aqui se genera una imagen de
estilo con Flux+LoRA (via fal) que luego entra como init_image (image-to-video).
Cambiar el style YAML cambia el look sin tocar nada mas.

Dos backends de imagen (D-051): `fal` (Flux + nano-banana/edit) y `google`
(Gemini 2.5 Flash Image, "nano-banana" nativo via google-genai). El humano elige
en Elegir (toggle); con `google` el pipeline corre sin fal (keyframe Gemini +
video Veo). El backend se resuelve por llamada, no por estilo.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .config import StyleConfig
from .contracts import Scene
from .settings import get_settings

logger = logging.getLogger(__name__)

# Modelo de imagen de Google (D-051). Gemini 2.5 Flash Image = "nano-banana" nativo;
# genera y EDITA (acepta imagenes de referencia -> consistencia + encadenado).
GOOGLE_IMAGE_MODEL = "gemini-2.5-flash-image"


def _extract_image_bytes(response) -> bytes | None:
    """Saca los bytes de la primera imagen de una respuesta de Gemini. Tolerante
    a la forma del SDK (inline_data en las parts del candidato). D-051."""
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                return data
    return None


def build_styled_prompt(scene: Scene, style: StyleConfig, framing: str = "") -> str:
    """Inyecta el prompt de la escena (+ el framing del plano) en el template de estilo.

    `framing` EXTIENDE el prompt de la escena (D-028): el plano hereda el setting
    y suma su encuadre. Sin framing, el prompt efectivo es el de la escena (clave
    de caché estable hacia atrás).
    """
    base = scene.prompt if not framing else f"{scene.prompt}, {framing}"
    return style.prompt_template.format(scene_prompt=base).strip()


class KeyframeGenerator:
    """Genera el keyframe de estilo por escena. `_submit_fal` aislado para tests.

    `backend` (D-051) elige el motor de imagen: 'fal' (default del estilo) o
    'google' (Gemini 2.5 Flash Image). Se resuelve por llamada (toggle en Elegir).
    """

    def __init__(self, style: StyleConfig, out_dir: Path = Path("out/keyframes"),
                 backend: str | None = None):
        self.style = style
        self.out_dir = out_dir
        # backend explicito (toggle) o el del estilo (fal por defecto).
        self.backend = (backend or style.keyframe.backend or "fal").lower()
        out_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, scene: Scene, ref_images: list[Path] | None = None,
                       seed: int | None = None, framing: str = "") -> Path:
        prompt = build_styled_prompt(scene, self.style, framing)
        return await self._render(prompt, ref_images, seed, self.out_dir / f"{scene.id}.png")

    async def generate_design(self, design_prompt: str, ref_images: list[Path],
                              seed: int | None = None) -> Path:
        """Casting/look-dev: combina imágenes de entrada (persona + LEGO) + prompt -> cara."""
        styled = self.style.prompt_template.format(scene_prompt=design_prompt).strip()
        return await self._render(styled, ref_images, seed, self.out_dir / f"cast_{seed}.png")

    async def _render(self, prompt: str, ref_images: list[Path] | None,
                      seed: int | None, dest: Path) -> Path:
        """Despacha al backend elegido (D-051). Devuelve el path local del PNG."""
        if self.backend == "google":
            return await self._submit_google(prompt, ref_images or [], seed, dest)
        if ref_images and self.style.keyframe.ref_model:
            url = await self._submit_ref(prompt, ref_images, seed)  # propaga identidad
        else:
            url = await self._submit_fal(prompt, seed)
        return await self._download(url, dest)

    async def _submit_google(self, prompt: str, ref_images: list[Path],
                             seed: int | None, dest: Path) -> Path:
        """Genera (o edita, si hay refs) con Gemini 2.5 Flash Image. I/O (smoke).

        Gemini no tiene `negative_prompt`: se anexa como "Avoid: ...". Las refs
        entran como imagenes del contenido -> edicion/encadenado + consistencia."""
        import asyncio

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Instala google-genai: uv add google-genai") from exc

        key = get_settings().require("google_api_key", "keyframe con Gemini (Google, D-051)")
        client = genai.Client(api_key=key)

        text = prompt
        if self.style.negative_prompt and not ref_images:
            text = f"{prompt}. Avoid: {self.style.negative_prompt}"
        contents: list = [text]
        for p in ref_images:  # refs como partes de imagen (edicion/identidad)
            contents.append(types.Part.from_bytes(
                data=Path(p).read_bytes(), mime_type="image/png"))

        config = None
        try:  # seed es best-effort: si el SDK/modelo no lo acepta, igual genera
            config = types.GenerateContentConfig(seed=seed) if seed is not None else None
        except Exception:  # noqa: BLE001
            config = None

        result = await asyncio.wait_for(asyncio.to_thread(
            client.models.generate_content,
            model=GOOGLE_IMAGE_MODEL, contents=contents, config=config,
        ), timeout=180)

        data = _extract_image_bytes(result)
        if data is None:
            raise RuntimeError("Gemini no devolvio imagen en la respuesta.")
        dest.write_bytes(data)
        return dest

    async def _submit_ref(self, prompt: str, ref_images: list[Path], seed: int | None = None) -> str:
        """Genera el keyframe condicionado a imágenes de referencia (consistencia)."""
        import asyncio
        import fal_client

        key = get_settings().require("fal_key", "keyframe con referencia de personaje")
        client = fal_client.AsyncClient(key=key)
        urls = [await client.upload_file(str(p)) for p in ref_images]
        arguments = {"prompt": prompt, "image_urls": urls}
        if seed is not None:
            arguments["seed"] = seed
        result = await asyncio.wait_for(
            client.subscribe(self.style.keyframe.ref_model, arguments=arguments),
            timeout=120,
        )
        images = result.get("images") or []
        if not images:
            raise RuntimeError(f"Respuesta de fal (ref) sin imagen: {result}")
        return images[0]["url"]

    async def _submit_fal(self, prompt: str, seed: int | None = None) -> str:
        import asyncio
        import fal_client

        key = get_settings().require("fal_key", "generacion de keyframes / capa de estilo")
        client = fal_client.AsyncClient(key=key)

        kf = self.style.keyframe
        arguments: dict = {"prompt": prompt}
        if seed is not None:
            arguments["seed"] = seed
        if self.style.negative_prompt:
            arguments["negative_prompt"] = self.style.negative_prompt
        if kf.lora and not kf.lora.startswith("<"):
            arguments["loras"] = [{"path": kf.lora, "scale": kf.strength}]

        result = await asyncio.wait_for(
            client.subscribe(kf.model, arguments=arguments),
            timeout=120,
        )
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
