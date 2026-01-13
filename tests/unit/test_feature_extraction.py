import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from models.domain import Sentiment


@dataclass
class FeatureData:
    feature_zh: str
    feature_en: str
    sentiment: str


class TestFeatureExtraction:

    def test_extract_features_from_snippet_single_feature(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[{"feature_zh": "油耗", "feature_en": "fuel consumption", "sentiment": "positive"}]'

        snippet = "奔驰GLE的油耗表现非常出色"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 1
        assert result[0]["feature_zh"] == "油耗"
        assert result[0]["feature_en"] == "fuel consumption"
        assert result[0]["sentiment"] == "positive"

    def test_extract_features_from_snippet_multiple_features(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '''[
            {"feature_zh": "油耗", "feature_en": "fuel consumption", "sentiment": "positive"},
            {"feature_zh": "空间", "feature_en": "space", "sentiment": "positive"},
            {"feature_zh": "价格", "feature_en": "price", "sentiment": "negative"}
        ]'''

        snippet = "奔驰GLE油耗低，空间大，但价格偏高"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 3
        assert result[0]["feature_zh"] == "油耗"
        assert result[1]["feature_zh"] == "空间"
        assert result[2]["feature_zh"] == "价格"
        assert result[2]["sentiment"] == "negative"

    def test_extract_features_from_snippet_empty(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[]'

        snippet = ""

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 0

    def test_extract_features_from_snippet_no_features_found(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[]'

        snippet = "这是一个普通的句子"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 0

    def test_extract_features_handles_invalid_json(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = 'not valid json'

        snippet = "奔驰GLE的油耗表现非常出色"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 0

    def test_extract_features_handles_partial_json(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[{"feature_zh": "油耗"'

        snippet = "奔驰GLE的油耗表现非常出色"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert len(result) == 0

    def test_extract_features_batch(self):
        from services.feature_extraction import extract_features_batch

        mock_ollama = AsyncMock()

        responses = [
            '[{"feature_zh": "油耗", "feature_en": "fuel consumption", "sentiment": "positive"}]',
            '[{"feature_zh": "空间", "feature_en": "space", "sentiment": "neutral"}]',
            '[]',
        ]
        mock_ollama._call_ollama.side_effect = responses

        snippets = [
            "奔驰GLE的油耗表现非常出色",
            "宝马X5的空间还可以",
            "这是一个普通句子",
        ]

        result = asyncio.run(extract_features_batch(snippets, mock_ollama))

        assert len(result) == 3
        assert len(result[0]) == 1
        assert result[0][0]["feature_zh"] == "油耗"
        assert len(result[1]) == 1
        assert result[1][0]["feature_zh"] == "空间"
        assert len(result[2]) == 0

    def test_extract_features_normalizes_sentiment(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[{"feature_zh": "油耗", "feature_en": "fuel", "sentiment": "POSITIVE"}]'

        snippet = "奔驰GLE的油耗表现非常出色"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert result[0]["sentiment"] == "positive"

    def test_extract_features_defaults_neutral_for_unknown_sentiment(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[{"feature_zh": "油耗", "feature_en": "fuel", "sentiment": "unknown"}]'

        snippet = "奔驰GLE的油耗"

        result = asyncio.run(extract_features_from_snippet(snippet, mock_ollama))

        assert result[0]["sentiment"] == "neutral"

    def test_extract_features_with_brand_context(self):
        from services.feature_extraction import extract_features_from_snippet

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '[{"feature_zh": "安全性", "feature_en": "safety", "sentiment": "positive"}]'

        snippet = "沃尔沃的安全性世界领先"
        brand_name = "沃尔沃"

        result = asyncio.run(
            extract_features_from_snippet(snippet, mock_ollama, brand_name=brand_name)
        )

        assert len(result) == 1
        assert result[0]["feature_zh"] == "安全性"


class TestFeatureExtractionPrompt:

    def test_prompt_includes_snippet(self):
        from services.feature_extraction import _build_extraction_prompt

        snippet = "奔驰GLE的油耗表现非常出色"

        prompt = _build_extraction_prompt(snippet)

        assert "奔驰GLE的油耗表现非常出色" in prompt

    def test_prompt_includes_brand_context(self):
        from services.feature_extraction import _build_extraction_prompt

        snippet = "油耗表现非常出色"
        brand_name = "奔驰"

        prompt = _build_extraction_prompt(snippet, brand_name=brand_name)

        assert "奔驰" in prompt

    def test_prompt_requests_json_format(self):
        from services.feature_extraction import _build_extraction_prompt

        snippet = "油耗表现出色"

        prompt = _build_extraction_prompt(snippet)

        assert "JSON" in prompt or "json" in prompt


class TestFeatureExtractionIntegration:

    def test_extract_features_for_mention(self):
        from services.feature_extraction import extract_features_for_mention

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.return_value = '''[
            {"feature_zh": "油耗", "feature_en": "fuel consumption", "sentiment": "positive"},
            {"feature_zh": "空间", "feature_en": "space", "sentiment": "neutral"}
        ]'''

        evidence_snippets = {
            "zh": ["奔驰GLE油耗低空间大"],
            "en": ["Mercedes GLE has low fuel consumption and large space"]
        }
        brand_name = "奔驰"

        result = asyncio.run(
            extract_features_for_mention(evidence_snippets, mock_ollama, brand_name)
        )

        assert len(result) == 2
        assert result[0]["feature_zh"] == "油耗"
        assert result[1]["feature_zh"] == "空间"

    def test_extract_features_for_mention_empty_snippets(self):
        from services.feature_extraction import extract_features_for_mention

        mock_ollama = AsyncMock()

        evidence_snippets = {"zh": [], "en": []}
        brand_name = "奔驰"

        result = asyncio.run(
            extract_features_for_mention(evidence_snippets, mock_ollama, brand_name)
        )

        assert len(result) == 0

    def test_extract_features_for_mention_multiple_snippets(self):
        from services.feature_extraction import extract_features_for_mention

        mock_ollama = AsyncMock()
        mock_ollama._call_ollama.side_effect = [
            '[{"feature_zh": "油耗", "feature_en": "fuel", "sentiment": "positive"}]',
            '[{"feature_zh": "安全", "feature_en": "safety", "sentiment": "positive"}]',
        ]

        evidence_snippets = {
            "zh": ["奔驰油耗低", "奔驰安全性好"],
            "en": ["Low fuel", "Good safety"]
        }
        brand_name = "奔驰"

        result = asyncio.run(
            extract_features_for_mention(evidence_snippets, mock_ollama, brand_name)
        )

        assert len(result) == 2
        feature_names = {f["feature_zh"] for f in result}
        assert "油耗" in feature_names
        assert "安全" in feature_names


class TestFeatureDataValidation:

    def test_validate_feature_data_valid(self):
        from services.feature_extraction import _validate_feature_data

        data = {"feature_zh": "油耗", "feature_en": "fuel", "sentiment": "positive"}

        result = _validate_feature_data(data)

        assert result is True

    def test_validate_feature_data_missing_zh(self):
        from services.feature_extraction import _validate_feature_data

        data = {"feature_en": "fuel", "sentiment": "positive"}

        result = _validate_feature_data(data)

        assert result is False

    def test_validate_feature_data_empty_zh(self):
        from services.feature_extraction import _validate_feature_data

        data = {"feature_zh": "", "feature_en": "fuel", "sentiment": "positive"}

        result = _validate_feature_data(data)

        assert result is False

    def test_validate_feature_data_missing_sentiment(self):
        from services.feature_extraction import _validate_feature_data

        data = {"feature_zh": "油耗", "feature_en": "fuel"}

        result = _validate_feature_data(data)

        assert result is True
