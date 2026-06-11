"""L6 - FusedGate: combina señales (VLM + CLIP + aesthetic) con umbral por clase.

Construye las señales disponibles (VLM siempre; CLIP/aesthetic si el extra
[vision] está instalado). Por escena: extrae un frame, corre cada señal, fusiona
ponderado y aplica el umbral de la clase. Degrada con elegancia: si no hay
ninguna señal disponible, gate permisivo (no bloquea smokes locales).
"""

from __future__ import annotations

from ..contracts import GateReport, GenResult, Scene
from .frames import extract_frame
from .fusion import build_report, enforce_verdict, fuse_signals
from .vlm import VLMSignal


def _build_default_signals(vlm_model: str | None = None) -> list:
    """VLM + identidad (Claude visión) siempre; CLIP/aesthetic si el extra [vision] está.

    vlm_model=None deshabilita la señal VLM (perfil con gate.enabled=false).
    """
    from .identity import IdentitySignal

    signals: list = [VLMSignal(vlm_model=vlm_model), IdentitySignal()]
    try:
        from .clip import ClipSignal

        signals.append(ClipSignal())
    except Exception:
        pass
    try:
        from .aesthetic import AestheticSignal

        signals.append(AestheticSignal())
    except Exception:
        pass
    return signals


class FusedGate:
    """Quality Gate "duro": fusión de señales + umbral por clase de escena."""

    def __init__(self, thresholds_by_class: dict[str, dict[str, float]],
                 signals: list | None = None, enforce: bool = False):
        self.thresholds_by_class = thresholds_by_class
        self.enforce = enforce  # suave por defecto: puntúa pero no bloquea
        self.signals = signals if signals is not None else _build_default_signals()

    def _thresholds_for(self, scene: Scene) -> dict[str, float]:
        return self.thresholds_by_class.get(scene.class_ or "standard", {})

    async def evaluate(self, scene: Scene, result: GenResult) -> GateReport:
        thresholds = self._thresholds_for(scene)
        try:
            frame = extract_frame(result.video_path)
        except Exception as exc:
            return GateReport(passed=True, reason=f"gate permisivo (sin frame: {exc})")

        outputs: list[tuple[dict, float]] = []
        used: list[str] = []
        for sig in self.signals:
            try:
                metrics = await sig.score(frame, scene)
            except Exception:
                continue
            if metrics:
                outputs.append((metrics, getattr(sig, "weight", 1.0)))
                used.append(getattr(sig, "name", "?"))

        if not outputs:
            return GateReport(passed=True, reason="gate permisivo (sin señales disponibles)")

        fused = fuse_signals(outputs)
        report = build_report(fused, thresholds, reason=f"señales: {','.join(used)}")
        return enforce_verdict(report, self.enforce)


# Compat: el nombre anterior apunta al gate fusionado (cli modo --brief).
VLMGate = FusedGate
