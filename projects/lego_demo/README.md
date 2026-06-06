# Ejemplo de referencia: `lego_demo`

Este es el **único proyecto versionado con su resultado** en el repo (todos los demás
artefactos generados están gitignored). Sirve para que veas el flujo completo —entrada,
decisión humana y salida— **sin generar nada ni gastar crédito**.

| Archivo | Qué es |
|---|---|
| [`project.yaml`](./project.yaml) | **La entrada.** Una escena LEGO, estilo `lego`, formato 9:16. |
| [`selections.yaml`](./selections.yaml) | **La decisión humana.** Qué keyframe se eligió para la escena `s1`. |
| [`keyframe_s1.png`](./keyframe_s1.png) | El **keyframe elegido** (imagen base de la escena), generado con Flux. |
| [`final_9x16.mp4`](./final_9x16.mp4) | El **video final** (1080×1920, ~5s), animado con Kling vía fal.ai. |

## Reproducirlo

```bash
uv run pipeline run lego_demo            # autónomo: la IA decide todo
# o el flujo AI-in-the-Loop:
uv run pipeline keyframes lego_demo --n 2
uv run pipeline pick lego_demo s1=0
uv run pipeline render lego_demo
```

> Re-correrlo sin cambios cuesta **$0** (caché). Esta corrida de ejemplo costó **$0.150**
> en fal.ai (1 clip de video, tier `volume`). Los `.png`/`.mp4` que generes localmente
> quedan ignorados por git; solo estos dos archivos curados están versionados.
