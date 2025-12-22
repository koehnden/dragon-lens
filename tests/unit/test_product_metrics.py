import pytest

from metrics.metrics import AnswerMetrics, visibility_metrics


def test_product_visibility_metrics_with_ranked_mentions():
    prompt_ids = [1, 2, 3, 4]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="RAV4", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=1, brand="CRV", rank=2, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="RAV4", rank=3, sentiment="negative"),
        AnswerMetrics(prompt_id=3, brand="RAV4", rank=None, sentiment="positive"),
        AnswerMetrics(prompt_id=3, brand="CRV", rank=1, sentiment="positive"),
    ]

    metrics = visibility_metrics(prompt_ids, mentions, "RAV4", ["CRV"])

    assert metrics["mention_rate"] == pytest.approx(0.75, rel=1e-2)
    assert metrics["share_of_voice"] == pytest.approx(0.479, rel=1e-2)
    assert metrics["top_spot_share"] == pytest.approx(0.25, rel=1e-2)
    assert metrics["sentiment_index"] == pytest.approx(2 / 3, rel=1e-2)
    assert metrics["dragon_lens_visibility"] == pytest.approx(0.47, rel=1e-2)


def test_product_metrics_zero_when_product_absent():
    prompt_ids = [1, 2]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="RAV4", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="RAV4", rank=2, sentiment="negative"),
    ]

    metrics = visibility_metrics(prompt_ids, mentions, "CRV", ["RAV4"])

    assert metrics["mention_rate"] == 0.0
    assert metrics["share_of_voice"] == 0.0
    assert metrics["top_spot_share"] == 0.0
    assert metrics["sentiment_index"] == 0.0
    assert metrics["dragon_lens_visibility"] == 0.0


def test_product_metrics_with_multiple_products_same_brand():
    prompt_ids = [1, 2, 3]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="RAV4", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=1, brand="Camry", rank=2, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="Camry", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=3, brand="CRV", rank=1, sentiment="neutral"),
    ]

    rav4_metrics = visibility_metrics(prompt_ids, mentions, "RAV4", ["Camry", "CRV"])
    camry_metrics = visibility_metrics(prompt_ids, mentions, "Camry", ["RAV4", "CRV"])

    assert rav4_metrics["mention_rate"] == pytest.approx(1 / 3, rel=1e-2)
    assert camry_metrics["mention_rate"] == pytest.approx(2 / 3, rel=1e-2)


def test_product_metrics_aggregation_across_prompts():
    prompt_ids = [1, 2, 3, 4, 5]
    mentions = [
        AnswerMetrics(prompt_id=1, brand="宋PLUS", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=2, brand="宋PLUS", rank=2, sentiment="positive"),
        AnswerMetrics(prompt_id=3, brand="宋PLUS", rank=1, sentiment="neutral"),
        AnswerMetrics(prompt_id=4, brand="汉EV", rank=1, sentiment="positive"),
        AnswerMetrics(prompt_id=5, brand="Model Y", rank=1, sentiment="positive"),
    ]

    song_plus_metrics = visibility_metrics(
        prompt_ids, mentions, "宋PLUS", ["汉EV", "Model Y"]
    )

    assert song_plus_metrics["mention_rate"] == pytest.approx(3 / 5, rel=1e-2)
    assert song_plus_metrics["top_spot_share"] == pytest.approx(2 / 5, rel=1e-2)
