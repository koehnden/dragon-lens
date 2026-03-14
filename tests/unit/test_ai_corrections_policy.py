import pytest


def test_policy_auto_applies_reject_with_lower_threshold():
    from services.ai_corrections.policy import (
        AICorrectionThresholds,
        ConfidenceLevel,
        MinConfidenceLevels,
        should_auto_apply,
    )

    thresholds = AICorrectionThresholds(
        reject_brand=0.8,
        reject_product=0.8,
        reject_mapping=0.8,
        validate=0.95,
        replace=0.95,
        add_mapping=0.95,
    )
    mins = MinConfidenceLevels(
        reject_brand=ConfidenceLevel.HIGH,
        reject_product=ConfidenceLevel.HIGH,
        reject_mapping=ConfidenceLevel.HIGH,
        validate=ConfidenceLevel.VERY_HIGH,
        replace=ConfidenceLevel.VERY_HIGH,
        add_mapping=ConfidenceLevel.VERY_HIGH,
    )
    ok = should_auto_apply(
        action="reject_brand",
        confidence_level=ConfidenceLevel.HIGH,
        confidence_score=0.81,
        evidence_quote_zh="耐克",
        prompt_response_zh="耐克是一个品牌。",
        thresholds=thresholds,
        min_levels=mins,
    )
    assert ok is True


def test_policy_does_not_auto_apply_replace_below_level():
    from services.ai_corrections.policy import (
        AICorrectionThresholds,
        ConfidenceLevel,
        MinConfidenceLevels,
        should_auto_apply,
    )

    thresholds = AICorrectionThresholds.default()
    mins = MinConfidenceLevels.default()
    ok = should_auto_apply(
        action="replace",
        confidence_level=ConfidenceLevel.HIGH,
        confidence_score=0.99,
        evidence_quote_zh="耐克",
        prompt_response_zh="耐克是一个品牌。",
        thresholds=thresholds,
        min_levels=mins,
    )
    assert ok is False


def test_policy_requires_evidence_quote_match():
    from services.ai_corrections.policy import (
        AICorrectionThresholds,
        ConfidenceLevel,
        MinConfidenceLevels,
        should_auto_apply,
    )

    thresholds = AICorrectionThresholds.default()
    mins = MinConfidenceLevels.default()
    ok = should_auto_apply(
        action="reject_brand",
        confidence_level=ConfidenceLevel.VERY_HIGH,
        confidence_score=0.99,
        evidence_quote_zh="阿迪达斯",
        prompt_response_zh="耐克是一个品牌。",
        thresholds=thresholds,
        min_levels=mins,
    )
    assert ok is False


def test_metrics_precision_recall_counts():
    from services.ai_corrections.metrics import compute_metrics

    metrics = compute_metrics(true_positives=3, false_positives=1, false_negatives=2)
    assert metrics["true_positives"] == 3
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 2
    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["recall"] == pytest.approx(0.6)

