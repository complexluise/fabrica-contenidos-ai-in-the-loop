"""Señal CLIP: adherencia numérica prompt↔frame (open_clip).

Determinista y barata una vez cargado el modelo. Requiere el extra [vision]
(torch + open_clip). Lazy: solo se importa al instanciar; si falta, FusedGate la
omite. Modelo ligero ViT-B/32 (CPU ok).
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import Scene


class ClipSignal:
    name = "clip"
    weight = 1.5  # señal numérica fuerte para adherencia

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k"):
        import open_clip  # lazy: requiere extra [vision]
        import torch

        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)

    async def score(self, frame: Path, scene: Scene) -> dict:
        from PIL import Image

        image = self.preprocess(Image.open(frame)).unsqueeze(0)
        text = self.tokenizer([scene.prompt])
        with self.torch.no_grad():
            img_emb = self.model.encode_image(image)
            txt_emb = self.model.encode_text(text)
            img_emb /= img_emb.norm(dim=-1, keepdim=True)
            txt_emb /= txt_emb.norm(dim=-1, keepdim=True)
            cosine = float((img_emb @ txt_emb.T).item())
        # cosine [-1,1] -> [0,1]
        return {"clip_adherence": max(0.0, min(1.0, (cosine + 1.0) / 2.0))}
