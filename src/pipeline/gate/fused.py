"""L6 - FusedGate: combina señales (VLM + CLIP + aesthetic) con umbral por clase.

Construye las señales disponibles (VLM siempre; CLIP/aesthetic si el extra
[vision] está instalado). Por plano: extrae frames, corre cada señal, fusiona
ponderado y aplica el umbral de la clase. Degrada con elegancia: si no hay
ninguna señal disponible, gate permisivo (no bloquea smokes locales).
"""

from __future__ import annotations

from ..contracts import GateReport, GenResult, ShotJob
from .frames import extract_frame, frame_times
from .fusion import build_report, enforce_verdict, fuse_signals
from .vlm import VLMSignal


def build_default_signals(vlm_model: str | None = None) -> list:
    """VLM + identidad (Claude visión) siempre; CLIP/aesthetic si el extra [vision] está.

    vlm_model=None deshabilita la señal VLM. `vlm_model` también gobierna a
    IdentitySignal (D-076): el perfil decide UN modelo de juicio, no dos.
    """
    from .identity import IdentitySignal

    signals: list = [VLMSignal(vlm_model=vlm_model), IdentitySignal(vlm_model=vlm_model)]
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
        self.signals = signals if signals is not None else build_default_signals()

    def _thresholds_for(self, job: ShotJob) -> dict[str, float]:
        return self.thresholds_by_class.get(job.class_ or "standard", {})

    async def evaluate(self, job: ShotJob, result: GenResult) -> GateReport:
        thresholds = self._thresholds_for(job)
        try:
            # D-069: el gate deja de ser ciego al movimiento — 3 muestras
            # cronológicas del clip; el VLM las ve TODAS (morphing/deriva/
            # movimiento roto), las señales de frame único reciben la del medio.
            from ..assemble import probe_duration
            dur = probe_duration(result.video_path)
            times = frame_times(dur) if dur else [1.0]
            frames = [extract_frame(result.video_path, t) for t in times]
            frame = frames[len(frames) // 2]
        except Exception as exc:
            return GateReport(passed=True, reason=f"gate permisivo (sin frame: {exc})")

        outputs: list[tuple[dict, float]] = []
        used: list[str] = []
        for sig in self.signals:
            try:
                if hasattr(sig, "score_frames"):
                    metrics = await sig.score_frames(frames, job)
                else:
                    metrics = await sig.score(frame, job)
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
