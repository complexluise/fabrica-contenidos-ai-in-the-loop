"""Core: el gate decide que pasa a ensamblaje. Umbral por tipo de escena.

Sprint 3: fusion de señales (VLM + CLIP + aesthetic) ponderada + umbral por clase.
"""

import pytest

from pipeline.gate import (
    build_report,
    enforce_verdict,
    fuse_signals,
    parse_judge_response,
    passes_threshold,
)
from pipeline.contracts import GateReport

HERO = {"aesthetic": 0.80, "char_consistency": 0.85, "clip_adherence": 0.75}


def test_passes_when_all_signals_above_threshold():
    rep = GateReport(passed=False, aesthetic=0.9, char_consistency=0.9, clip_adherence=0.8)
    assert passes_threshold(rep, HERO) is True


def test_fails_when_one_signal_below():
    rep = GateReport(passed=False, aesthetic=0.9, char_consistency=0.5, clip_adherence=0.8)
    assert passes_threshold(rep, HERO) is False


def test_high_artifacts_fail_even_if_scores_ok():
    rep = GateReport(passed=False, aesthetic=0.9, char_consistency=0.9, clip_adherence=0.8, artifacts=0.7)
    assert passes_threshold(rep, HERO) is False


def test_parse_judge_extracts_json_and_applies_threshold():
    text = 'Analisis... {"aesthetic":0.9,"char_consistency":0.9,"clip_adherence":0.8,"artifacts":0.1,"reason":"ok"} fin'
    rep = parse_judge_response(text, HERO)
    assert rep.passed is True and rep.reason == "ok"


def test_parse_judge_raises_without_json():
    with pytest.raises(ValueError):
        parse_judge_response("sin json aqui", HERO)


# --- Sprint 3: fusion de señales -------------------------------------------

def test_fuse_weighted_mean_per_metric():
    out = fuse_signals([({"clip_adherence": 0.8}, 1.0), ({"clip_adherence": 0.4}, 1.0)])
    assert out["clip_adherence"] == pytest.approx(0.6)


def test_fuse_respects_weights():
    out = fuse_signals([({"aesthetic": 1.0}, 3.0), ({"aesthetic": 0.0}, 1.0)])
    assert out["aesthetic"] == pytest.approx(0.75)


def test_fuse_combines_disjoint_metrics():
    # VLM da varias señales; CLIP solo adherencia; aesthetic solo estetica.
    out = fuse_signals([
        ({"clip_adherence": 0.9}, 2.0),            # CLIP (peso alto en adherencia)
        ({"aesthetic": 0.7}, 1.0),                 # aesthetic
        ({"clip_adherence": 0.6, "char_consistency": 0.8, "aesthetic": 0.5}, 1.0),  # VLM
    ])
    assert out["clip_adherence"] == pytest.approx((0.9 * 2 + 0.6) / 3)
    assert out["char_consistency"] == pytest.approx(0.8)
    assert out["aesthetic"] == pytest.approx((0.7 + 0.5) / 2)


def test_fuse_empty_returns_empty():
    assert fuse_signals([]) == {}


def test_build_report_applies_threshold_pass():
    rep = build_report(
        {"aesthetic": 0.9, "char_consistency": 0.9, "clip_adherence": 0.8}, HERO
    )
    assert rep.passed is True
    assert rep.clip_adherence == 0.8


def test_build_report_fails_below_threshold():
    rep = build_report({"clip_adherence": 0.5}, HERO)
    assert rep.passed is False


# --- Sprint 3: modo suave (no bloquea regeneraciones mientras iteras) -------

def test_soft_mode_always_passes_but_keeps_scores():
    rep = GateReport(passed=False, aesthetic=0.1, clip_adherence=0.2)
    out = enforce_verdict(rep, enforce=False)
    assert out.passed is True            # no bloquea
    assert out.aesthetic == 0.1          # conserva el score real para calibrar


def test_strict_mode_keeps_verdict():
    rep = GateReport(passed=False, aesthetic=0.1)
    assert enforce_verdict(rep, enforce=True).passed is False
