import pytest


class TestCombinedScoreCalculation:

    def test_calculate_combined_score_all_positive(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=10, positive_count=10, neutral_count=0, negative_count=0
        )

        assert score == 10.0

    def test_calculate_combined_score_all_negative(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=10, positive_count=0, neutral_count=0, negative_count=10
        )

        assert score == 0.0

    def test_calculate_combined_score_all_neutral(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=10, positive_count=0, neutral_count=10, negative_count=0
        )

        assert score == 5.0

    def test_calculate_combined_score_mixed_sentiment(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=10, positive_count=6, neutral_count=2, negative_count=2
        )

        assert 5.0 < score < 10.0

    def test_calculate_combined_score_zero_frequency(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=0, positive_count=5, neutral_count=0, negative_count=0
        )

        assert score == 0.0

    def test_calculate_combined_score_zero_mentions(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=10, positive_count=0, neutral_count=0, negative_count=0
        )

        assert score == 0.0

    def test_combined_score_formula(self):
        from services.feature_metrics_service import calculate_combined_score

        score = calculate_combined_score(
            frequency=8, positive_count=3, neutral_count=2, negative_count=1
        )

        total = 3 + 2 + 1
        sentiment_weight = (3 - 1) / total
        normalized = (sentiment_weight + 1) / 2
        expected = 8 * normalized

        assert pytest.approx(score, 0.01) == expected


class TestFeatureScoreDataclass:

    def test_feature_score_creation(self):
        from services.feature_metrics_service import FeatureScore

        score = FeatureScore(
            feature_id=1,
            feature_name_zh="油耗",
            feature_name_en="fuel consumption",
            frequency=10,
            positive_count=8,
            neutral_count=1,
            negative_count=1,
            combined_score=7.0,
        )

        assert score.feature_id == 1
        assert score.feature_name_zh == "油耗"
        assert score.frequency == 10

    def test_feature_score_optional_en_name(self):
        from services.feature_metrics_service import FeatureScore

        score = FeatureScore(
            feature_id=1,
            feature_name_zh="油耗",
            feature_name_en=None,
            frequency=5,
            positive_count=3,
            neutral_count=1,
            negative_count=1,
            combined_score=3.5,
        )

        assert score.feature_name_en is None


class TestEntityFeatureData:

    def test_entity_feature_data_creation(self):
        from services.feature_metrics_service import EntityFeatureData, FeatureScore

        feature = FeatureScore(
            feature_id=1,
            feature_name_zh="油耗",
            feature_name_en="fuel",
            frequency=5,
            positive_count=3,
            neutral_count=1,
            negative_count=1,
            combined_score=3.5,
        )

        entity_data = EntityFeatureData(
            entity_id=1,
            entity_name="奔驰",
            entity_type="brand",
            features=[feature],
        )

        assert entity_data.entity_id == 1
        assert entity_data.entity_name == "奔驰"
        assert len(entity_data.features) == 1


class TestSpiderChartData:

    def test_spider_chart_data_creation(self):
        from services.feature_metrics_service import (
            EntityFeatureData,
            FeatureScore,
            SpiderChartData,
        )

        feature = FeatureScore(
            feature_id=1,
            feature_name_zh="油耗",
            feature_name_en="fuel",
            frequency=5,
            positive_count=3,
            neutral_count=1,
            negative_count=1,
            combined_score=3.5,
        )

        entity = EntityFeatureData(
            entity_id=1,
            entity_name="奔驰",
            entity_type="brand",
            features=[feature],
        )

        chart_data = SpiderChartData(
            run_id=1,
            vertical_id=1,
            vertical_name="SUV",
            top_features=["油耗", "空间", "安全"],
            entities=[entity],
        )

        assert chart_data.run_id == 1
        assert len(chart_data.top_features) == 3
        assert len(chart_data.entities) == 1


class TestNormalizedScoring:

    def test_score_range_0_to_frequency(self):
        from services.feature_metrics_service import calculate_combined_score

        for freq in [1, 5, 10, 100]:
            for pos in range(0, freq + 1, max(1, freq // 5)):
                neg = freq - pos
                score = calculate_combined_score(
                    frequency=freq,
                    positive_count=pos,
                    neutral_count=0,
                    negative_count=neg,
                )
                assert 0.0 <= score <= freq

    def test_score_increases_with_positive_sentiment(self):
        from services.feature_metrics_service import calculate_combined_score

        score_negative = calculate_combined_score(
            frequency=10, positive_count=0, neutral_count=0, negative_count=10
        )
        score_neutral = calculate_combined_score(
            frequency=10, positive_count=0, neutral_count=10, negative_count=0
        )
        score_positive = calculate_combined_score(
            frequency=10, positive_count=10, neutral_count=0, negative_count=0
        )

        assert score_negative < score_neutral < score_positive
