"""L6 - Lógica pura del gate: scoring, fusión de señales y umbral.

Sin I/O ni red -> core testeable. Las señales (VLM/CLIP/aesthetic) producen
métricas parciales; aquí se fusionan ponderadas y se comparan contra el umbral
por clase de escena.
"""

from __future__ import annotations

import json

from ..contracts import GateReport

_METRICS = ("aesthetic", "char_consistency", "clip_adherence", "artifacts")


def gate_score(report: GateReport) -> float:
    """Score compuesto para elegir el mejor candidato (Ensemble). Mayor = mejor."""
    return (
        report.aesthetic
        + report.char_consistency
        + report.clip_adherence
        - report.artifacts
    )


def passes_threshold(report: GateReport, thresholds: dict[str, float]) -> bool:
    """True si todas las señales presentes superan su umbral. Lógica pura."""
    checks = {
        "aesthetic": report.aesthetic,
        "char_consistency": report.char_consistency,
        "clip_adherence": report.clip_adherence,
    }
    for key, threshold in thresholds.items():
        if checks.get(key, 0.0) < threshold:
            return False
    return report.artifacts <= 0.5  # artefactos: más alto = peor


def fuse_signals(outputs: list[tuple[dict, float]]) -> dict:
    """Fusiona señales en métricas únicas: media ponderada por métrica.

    `outputs`: lista de (métricas, peso). Cada métrica se promedia solo sobre las
    señales que la aportan (una señal puede dar un subconjunto).
    """
    acc: dict[str, list[float]] = {}  # key -> [sum_w*v, sum_w]
    for metrics, weight in outputs:
        for key, value in metrics.items():
            slot = acc.setdefault(key, [0.0, 0.0])
            slot[0] += weight * float(value)
            slot[1] += weight
    return {k: (sv / sw if sw else 0.0) for k, (sv, sw) in acc.items()}


def build_report(metrics: dict, thresholds: dict[str, float], reason: str = "") -> GateReport:
    """Construye un GateReport desde métricas fusionadas y aplica el umbral."""
    report = GateReport(
        passed=False,
        aesthetic=float(metrics.get("aesthetic", 0.0)),
        char_consistency=float(metrics.get("char_consistency", 0.0)),
        clip_adherence=float(metrics.get("clip_adherence", 0.0)),
        artifacts=float(metrics.get("artifacts", 0.0)),
        reason=reason,
    )
    report.passed = passes_threshold(report, thresholds)
    return report


def report_scores(report: GateReport) -> dict:
    """Scores del gate como dict (para persistir en report/manifest y calibrar)."""
    return {
        "aesthetic": round(report.aesthetic, 3),
        "char_consistency": round(report.char_consistency, 3),
        "clip_adherence": round(report.clip_adherence, 3),
        "artifacts": round(report.artifacts, 3),
    }


def enforce_verdict(report: GateReport, enforce: bool) -> GateReport:
    """Modo suave vs estricto.

    En modo suave (enforce=False) el gate NO bloquea: fuerza passed=True pero
    conserva los scores reales para calibrar umbrales con datos más adelante.
    En estricto deja el veredicto tal cual (puede disparar reintento/escalado).
    """
    if not enforce and not report.passed:
        report.passed = True
        report.reason = (report.reason + " · gate suave (no bloquea)").lstrip(" ·")
    return report


def parse_judge_metrics(text: str) -> tuple[dict, str]:
    """Extrae métricas + reason del JSON del juez VLM. Testeable."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Respuesta del juez sin JSON: {text[:200]}")
    data = json.loads(text[start : end + 1])
    metrics = {k: float(data.get(k, 0.0)) for k in _METRICS}
    return metrics, str(data.get("reason", ""))


def parse_judge_response(text: str, thresholds: dict[str, float]) -> GateReport:
    """Compat: parsea el veredicto del juez y aplica umbral -> GateReport."""
    metrics, reason = parse_judge_metrics(text)
    return build_report(metrics, thresholds, reason)
