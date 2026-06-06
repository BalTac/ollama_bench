"""Scoring — separazione qualità vs performance.

Quality score (canonico):
- Se il prompt ha deterministic_checks: 45% deterministico + 55% giudice.
- Senza deterministic_checks (backward compat): 100% giudice.

Performance score (separato, non usato nel ranking quality):
- token/s normalizzato su soglia 100 tok/s.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

from benchmark.judge import JudgeScore
from benchmark.deterministic_scoring import DeterministicResults
from benchmark.metrics import ExtractedMetrics

logger = logging.getLogger(__name__)


@dataclass
class CompositeScore:
    """Score composito per un singolo prompt."""

    # Metriche oggettive
    latency_ms: float = 0.0
    tokens_per_sec: float = 0.0
    total_tokens: int = 0
    char_count: int = 0
    json_valid: int = 0
    format_valid: int = 0

    # Deterministico
    det_overall: float = 0.0
    det_performed: list[str] = None

    # Giudice (solo soggettive)
    accuracy: float = 0.0
    reasoning: float = 0.0
    coding: float = 0.0
    hallucination_risk: float = 0.0
    judge_overall: float = 0.0

    # Composito pesato
    weighted_score: float = 0.0
    quality_score: float = 0.0
    performance_score: float = 0.0
    weight: float = 1.0

    def __post_init__(self):
        if self.det_performed is None:
            self.det_performed = []


def compute_score(
    metrics: ExtractedMetrics,
    judge_score: JudgeScore,
    weight: float = 1.0,
    det_results: Optional[DeterministicResults] = None,
) -> CompositeScore:
    """Calcola quality score (canonico) e performance score (separato)."""

    tps_normalized = min(1.0, metrics.tokens_per_sec / 100.0)

    has_deterministic = (
        det_results is not None and len(det_results.performed_checks) > 0
    )

    if has_deterministic:
        quality_score = (
            0.45 * det_results.overall
            + 0.55 * judge_score.overall
        )
    else:
        quality_score = judge_score.overall

    performance_score = tps_normalized

    weighted = quality_score * weight

    return CompositeScore(
        latency_ms=metrics.latency_ms,
        tokens_per_sec=metrics.tokens_per_sec,
        total_tokens=metrics.total_tokens,
        char_count=metrics.char_count,
        json_valid=metrics.json_valid,
        format_valid=metrics.format_valid,
        det_overall=det_results.overall if det_results else 0.0,
        det_performed=list(det_results.performed_checks) if det_results else [],
        accuracy=judge_score.accuracy,
        reasoning=judge_score.reasoning,
        coding=judge_score.coding,
        hallucination_risk=judge_score.hallucination_risk,
        judge_overall=judge_score.overall,
        weighted_score=weighted,
        quality_score=quality_score,
        performance_score=performance_score,
        weight=weight,
    )


def compute_suite_score(scores: list[CompositeScore]) -> dict:
    """Aggrega score per una suite.

    Restituisce dizionario con medie e totali.
    """
    if not scores:
        return {"avg_overall": 0.0, "avg_latency_ms": 0.0, "prompt_count": 0}

    return {
        "avg_weighted_score": statistics.mean(s.weighted_score for s in scores),
        "avg_quality_score": statistics.mean(s.quality_score for s in scores),
        "avg_performance_score": statistics.mean(s.performance_score for s in scores),
        "avg_judge_overall": statistics.mean(s.judge_overall for s in scores),
        "avg_det_overall": statistics.mean(s.det_overall for s in scores),
        "avg_latency_ms": statistics.mean(s.latency_ms for s in scores),
        "avg_tokens_per_sec": statistics.mean(s.tokens_per_sec for s in scores),
        "avg_accuracy": statistics.mean(s.accuracy for s in scores),
        "avg_reasoning": statistics.mean(s.reasoning for s in scores),
        "avg_coding": statistics.mean(s.coding for s in scores),
        "avg_hallucination_risk": statistics.mean(s.hallucination_risk for s in scores),
        "avg_json_valid": statistics.mean(s.json_valid for s in scores),
        "avg_format_valid": statistics.mean(s.format_valid for s in scores),
        "prompt_count": len(scores),
    }
