from __future__ import annotations

import enum
from dataclasses import dataclass


class ConfidenceLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass(frozen=True)
class AICorrectionThresholds:
    reject_brand: float
    reject_product: float
    reject_mapping: float
    validate: float
    replace: float
    add_mapping: float

    @classmethod
    def default(cls) -> "AICorrectionThresholds":
        return cls(0.85, 0.85, 0.85, 0.95, 0.95, 0.95)


@dataclass(frozen=True)
class MinConfidenceLevels:
    reject_brand: ConfidenceLevel
    reject_product: ConfidenceLevel
    reject_mapping: ConfidenceLevel
    validate: ConfidenceLevel
    replace: ConfidenceLevel
    add_mapping: ConfidenceLevel

    @classmethod
    def default(cls) -> "MinConfidenceLevels":
        return cls(
            ConfidenceLevel.HIGH,
            ConfidenceLevel.HIGH,
            ConfidenceLevel.HIGH,
            ConfidenceLevel.VERY_HIGH,
            ConfidenceLevel.VERY_HIGH,
            ConfidenceLevel.VERY_HIGH,
        )


def should_auto_apply(
    action: str,
    confidence_level: ConfidenceLevel,
    confidence_score: float,
    evidence_quote_zh: str | None,
    prompt_response_zh: str,
    thresholds: AICorrectionThresholds,
    min_levels: MinConfidenceLevels,
) -> bool:
    if not _evidence_ok(evidence_quote_zh, prompt_response_zh):
        return False
    if confidence_score < _threshold_for(action, thresholds):
        return False
    return _level_rank(confidence_level) >= _level_rank(_min_level_for(action, min_levels))


def _evidence_ok(evidence_quote_zh: str | None, prompt_response_zh: str) -> bool:
    quote = (evidence_quote_zh or "").strip()
    return bool(quote) and quote in (prompt_response_zh or "")


def _threshold_for(action: str, thresholds: AICorrectionThresholds) -> float:
    return float(getattr(thresholds, action))


def _min_level_for(action: str, levels: MinConfidenceLevels) -> ConfidenceLevel:
    return getattr(levels, action)


def _level_rank(level: ConfidenceLevel) -> int:
    return {
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.MEDIUM: 2,
        ConfidenceLevel.HIGH: 3,
        ConfidenceLevel.VERY_HIGH: 4,
    }[level]

