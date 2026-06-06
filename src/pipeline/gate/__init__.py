"""L6 - Quality Gate. Fusión de señales (VLM + CLIP + aesthetic) con umbral por clase."""

from .frames import extract_frame
from .fused import FusedGate, VLMGate
from .fusion import (
    build_report,
    enforce_verdict,
    fuse_signals,
    gate_score,
    parse_judge_metrics,
    parse_judge_response,
    passes_threshold,
    report_scores,
)
from .vlm import VLMSignal

__all__ = [
    "FusedGate",
    "VLMGate",
    "VLMSignal",
    "extract_frame",
    "build_report",
    "enforce_verdict",
    "fuse_signals",
    "gate_score",
    "parse_judge_metrics",
    "parse_judge_response",
    "passes_threshold",
    "report_scores",
]
