from src.metrics.metrics import (
    AnswerMetrics,
    brand_mentions_for_prompt,
    mention_weight,
    visibility_metrics,
)


def test_visibility_metrics_with_mixed_mentions():
    prompts = [1, 2, 3, 4]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="BrandA", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=1, brand="BrandB", rank=2, sentiment="neutral"),
        AnswerMetrics(prompt_id=2, brand="BrandA", rank=2, sentiment="negative"),
        AnswerMetrics(prompt_id=2, brand="BrandB", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=3, brand="BrandB", rank=1, sentiment="positive"),
    ]
    metrics = visibility_metrics(
        prompt_ids=prompts,
        mentions=mentions,
        brand="BrandA",
        competitor_brands=["BrandB"],
        weights=(0.4, 0.4, 0.2),
    )

    assert round(metrics["ASoV_coverage"], 2) == 0.5
    assert round(metrics["ASoV_relative"], 2) == 0.4
    assert round(metrics["Prominence Score"], 2) == 0.85
    assert round(metrics["Top-Spot Share"], 2) == 0.25
    assert round(metrics["Sentiment Index"], 2) == 0.0
    assert round(metrics["Positive Share"], 2) == 0.5
    assert round(metrics["Opportunity Rate"], 2) == 0.25
    assert round(metrics["Dragon Visibility Score"], 2) == 64.0


def test_metrics_handle_empty_data():
    metrics = visibility_metrics(
        prompt_ids=[],
        mentions=[],
        brand="BrandZ",
        competitor_brands=["BrandY"],
    )

    assert metrics["ASoV_coverage"] == 0.0
    assert metrics["ASoV_relative"] == 0.0
    assert metrics["Prominence Score"] == 0.0
    assert metrics["Top-Spot Share"] == 0.0
    assert metrics["Sentiment Index"] == 0.0
    assert metrics["Positive Share"] == 0.0
    assert metrics["Opportunity Rate"] == 0.0
    assert metrics["Dragon Visibility Score"] == 0.0


def test_weight_function_decreases_linearly():
    assert mention_weight(1) == 1.0
    assert mention_weight(2) == 0.7
    assert mention_weight(3) == 0.4
    assert mention_weight(4) == 0.1
    assert mention_weight(5) == 0.0


def test_prompt_filtering_selects_prompt_mentions():
    mentions = [
        AnswerMetrics(prompt_id=1, brand="BrandA", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="BrandA", rank=2, sentiment="negative"),
        AnswerMetrics(prompt_id=1, brand="BrandB", rank=None, sentiment="neutral"),
    ]

    prompt_mentions = brand_mentions_for_prompt(mentions, 1)
    assert len(prompt_mentions) == 2
    assert {m.brand for m in prompt_mentions} == {"BrandA", "BrandB"}
