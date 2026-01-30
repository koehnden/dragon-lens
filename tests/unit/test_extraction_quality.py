"""Test extraction quality assessment and retry logic."""

import pytest

from services.brand_recognition.models import (
    ExtractionResult,
    ExtractionQuality,
)
from services.brand_recognition.orchestrator import _assess_extraction_quality


class TestExtractionQuality:
    """Tests for ExtractionQuality dataclass."""

    def test_quality_defaults(self):
        quality = ExtractionQuality()
        assert quality.expected_count is None
        assert quality.list_item_count == 0
        assert quality.extracted_count == 0
        assert quality.is_sufficient is True
        assert quality.warning_message is None

    def test_quality_with_values(self):
        quality = ExtractionQuality(
            expected_count=10,
            list_item_count=10,
            extracted_count=8,
            is_sufficient=False,
            warning_message="Extracted 8 entities but expected at least 10",
        )
        assert quality.expected_count == 10
        assert quality.list_item_count == 10
        assert quality.extracted_count == 8
        assert quality.is_sufficient is False
        assert "8" in quality.warning_message
        assert "10" in quality.warning_message


class TestAssessExtractionQuality:
    """Tests for _assess_extraction_quality function."""

    def test_sufficient_extraction(self):
        result = ExtractionResult(
            brands={"Toyota": ["Toyota"], "Honda": ["Honda"]},
            products={"RAV4": ["RAV4"], "CR-V": ["CR-V"]},
        )
        quality = _assess_extraction_quality(
            text="TOP 4 SUVs",
            result=result,
            expected_count=4,
            list_item_count=4,
        )
        assert quality.is_sufficient is True
        assert quality.extracted_count == 4
        assert quality.expected_count == 4
        assert quality.warning_message is None

    def test_insufficient_extraction(self):
        result = ExtractionResult(
            brands={"Toyota": ["Toyota"]},
            products={"RAV4": ["RAV4"]},
        )
        quality = _assess_extraction_quality(
            text="TOP 10 SUVs",
            result=result,
            expected_count=10,
            list_item_count=10,
        )
        assert quality.is_sufficient is False
        assert quality.extracted_count == 2
        assert quality.expected_count == 10
        assert quality.warning_message is not None
        assert "2" in quality.warning_message
        assert "10" in quality.warning_message

    def test_no_expected_count(self):
        result = ExtractionResult(
            brands={"Toyota": ["Toyota"]},
            products={},
        )
        quality = _assess_extraction_quality(
            text="Some text without TOP pattern",
            result=result,
            expected_count=None,
            list_item_count=0,
        )
        assert quality.is_sufficient is True
        assert quality.expected_count is None
        assert quality.warning_message is None

    def test_uses_list_item_count_when_no_expected(self):
        result = ExtractionResult(
            brands={"A": ["A"]},
            products={},
        )
        quality = _assess_extraction_quality(
            text="1. Item one\n2. Item two\n3. Item three",
            result=result,
            expected_count=None,
            list_item_count=3,
        )
        # With no explicit expected count but list_item_count = 3,
        # and only 1 entity extracted, it should be insufficient
        assert quality.is_sufficient is False
        assert quality.list_item_count == 3
        assert quality.extracted_count == 1

    def test_empty_extraction(self):
        result = ExtractionResult(
            brands={},
            products={},
        )
        quality = _assess_extraction_quality(
            text="TOP 5 recommendations",
            result=result,
            expected_count=5,
            list_item_count=5,
        )
        assert quality.is_sufficient is False
        assert quality.extracted_count == 0

    def test_over_extraction_is_sufficient(self):
        result = ExtractionResult(
            brands={"A": ["A"], "B": ["B"], "C": ["C"]},
            products={"X": ["X"], "Y": ["Y"], "Z": ["Z"]},
        )
        quality = _assess_extraction_quality(
            text="TOP 5 items",
            result=result,
            expected_count=5,
            list_item_count=5,
        )
        # Extracted 6, expected 5 - should be sufficient
        assert quality.is_sufficient is True
        assert quality.extracted_count == 6


class TestExtractionResultWithQuality:
    """Tests for ExtractionResult with quality field."""

    def test_result_includes_quality(self):
        quality = ExtractionQuality(
            expected_count=10,
            list_item_count=10,
            extracted_count=8,
            is_sufficient=False,
            warning_message="Extracted 8 entities but expected at least 10",
        )
        result = ExtractionResult(
            brands={"Toyota": ["Toyota"]},
            products={"RAV4": ["RAV4"]},
            quality=quality,
        )
        assert result.quality is not None
        assert result.quality.expected_count == 10
        assert result.quality.is_sufficient is False

    def test_result_quality_defaults_to_none(self):
        result = ExtractionResult(
            brands={},
            products={},
        )
        assert result.quality is None
