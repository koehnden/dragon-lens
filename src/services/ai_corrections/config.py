from __future__ import annotations

from typing import Any

from services.ai_corrections.policy import AICorrectionThresholds, ConfidenceLevel, MinConfidenceLevels


def merge_thresholds(overrides: dict[str, Any] | None) -> AICorrectionThresholds:
    base = AICorrectionThresholds.default()
    values = {**base.__dict__, **{k: v for k, v in (overrides or {}).items() if v is not None}}
    return AICorrectionThresholds(**values)


def merge_min_levels(overrides: dict[str, Any] | None) -> MinConfidenceLevels:
    base = MinConfidenceLevels.default()
    values = {**base.__dict__, **_levels(overrides or {})}
    return MinConfidenceLevels(**values)


def _levels(overrides: dict[str, Any]) -> dict[str, ConfidenceLevel]:
    result: dict[str, ConfidenceLevel] = {}
    for k, v in overrides.items():
        if v is None:
            continue
        result[k] = ConfidenceLevel(str(v).upper())
    return result

