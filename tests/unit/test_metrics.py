import pytest

from metrics.metrics import AnswerMetrics, visibility_metrics


def test_visibility_metrics_with_ranked_mentions():
    prompt_ids = [1, 2, 3, 4]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="Alpha", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=1, brand="Beta", rank=2, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="Alpha", rank=3, sentiment="negative"),
        AnswerMetrics(prompt_id=3, brand="Alpha", rank=None, sentiment="positive"),
        AnswerMetrics(prompt_id=3, brand="Beta", rank=1, sentiment="positive"),
    ]

    metrics = visibility_metrics(prompt_ids, mentions, "Alpha", ["Beta"])

    assert metrics["mention_rate"] == pytest.approx(0.75, rel=1e-2)
    assert metrics["share_of_voice"] == pytest.approx(0.479, rel=1e-2)
    assert metrics["top_spot_share"] == pytest.approx(0.25, rel=1e-2)
    assert metrics["sentiment_index"] == pytest.approx(2 / 3, rel=1e-2)
    assert metrics["dragon_lens_visibility"] == pytest.approx(0.471, rel=1e-2)


def test_metrics_zero_when_brand_absent():
    prompt_ids = [1, 2]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="Beta", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="Beta", rank=2, sentiment="negative"),
    ]

    metrics = visibility_metrics(prompt_ids, mentions, "Gamma", ["Beta"])

    assert metrics["mention_rate"] == 0.0
    assert metrics["share_of_voice"] == 0.0
    assert metrics["top_spot_share"] == 0.0
    assert metrics["sentiment_index"] == 0.0
    assert metrics["dragon_lens_visibility"] == 0.0
