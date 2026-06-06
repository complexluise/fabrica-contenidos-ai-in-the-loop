"""Señal estética (LAION aesthetic predictor: MLP lineal sobre embeddings CLIP).

Requiere el extra [vision] y los pesos del predictor (no incluidos). Lazy; si
falta el modelo o los pesos, FusedGate la omite. Estructura estándar LAION:
CLIP ViT-L/14 -> MLP -> score 1..10, normalizado a 0..1.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..contracts import Scene


class AestheticSignal:
    name = "aesthetic"
    weight = 1.0

    def __init__(self, weights_path: str | None = None):
        weights_path = weights_path or os.environ.get("AESTHETIC_WEIGHTS")
        if not weights_path or not Path(weights_path).exists():
            raise RuntimeError(
                "Falta el modelo de estética (AESTHETIC_WEIGHTS). Señal omitida."
            )
        import open_clip  # lazy: extra [vision]
        import torch

        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-L-14", pretrained="openai"
        )
        self.model.eval()
        # MLP lineal estándar del aesthetic predictor (768 -> 1).
        self.head = torch.nn.Linear(768, 1)
        self.head.load_state_dict(torch.load(weights_path, map_location="cpu"))
        self.head.eval()

    async def score(self, frame: Path, scene: Scene) -> dict:
        from PIL import Image

        image = self.preprocess(Image.open(frame)).unsqueeze(0)
        with self.torch.no_grad():
            emb = self.model.encode_image(image)
            emb /= emb.norm(dim=-1, keepdim=True)
            raw = float(self.head(emb).item())  # ~1..10
        return {"aesthetic": max(0.0, min(1.0, raw / 10.0))}
