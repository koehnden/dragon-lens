import pytest
from unittest.mock import MagicMock, patch

from services.brand_recognition.product_brand_mapping import (
    _get_or_create_knowledge_brand,
    _get_or_create_knowledge_product,
    _upsert_knowledge_mapping,
)


def test_get_or_create_knowledge_brand_returns_existing():
    db = MagicMock()
    existing_brand = MagicMock()
    existing_brand.id = 1
    db.query.return_value.filter.return_value.first.return_value = existing_brand

    result = _get_or_create_knowledge_brand(db, 1, "Toyota")

    assert result == existing_brand
    db.add.assert_not_called()


def test_get_or_create_knowledge_brand_creates_new():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    result = _get_or_create_knowledge_brand(db, 1, "Toyota")

    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert result.display_name == "Toyota"
    assert result.is_validated is False


def test_get_or_create_knowledge_product_returns_existing():
    db = MagicMock()
    existing_product = MagicMock()
    existing_product.id = 1
    db.query.return_value.filter.return_value.first.return_value = existing_product

    result = _get_or_create_knowledge_product(db, 1, "RAV4")

    assert result == existing_product
    db.add.assert_not_called()


def test_get_or_create_knowledge_product_creates_new():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    result = _get_or_create_knowledge_product(db, 1, "RAV4")

    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert result.display_name == "RAV4"
    assert result.is_validated is False


def test_upsert_knowledge_mapping_creates_new():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    result = _upsert_knowledge_mapping(db, 1, 10, 20, "auto_proximity")

    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert result.product_id == 10
    assert result.brand_id == 20
    assert result.source == "auto_proximity"
    assert result.is_validated is False
    assert result.support_count == 0
    assert result.confidence == 0.0


def test_upsert_knowledge_mapping_preserves_feedback_source():
    db = MagicMock()
    existing = MagicMock()
    existing.source = "feedback"
    existing.is_validated = True
    db.query.return_value.filter.return_value.first.return_value = existing
    existing.support_count = 5

    result = _upsert_knowledge_mapping(db, 1, 10, 20, "auto_list_evidence", 2)

    assert result == existing
    assert result.source == "feedback"
    assert result.support_count == 7


def test_upsert_knowledge_mapping_preserves_user_reject_source():
    db = MagicMock()
    existing = MagicMock()
    existing.source = "user_reject"
    existing.is_validated = False
    db.query.return_value.filter.return_value.first.return_value = existing
    existing.support_count = 5

    result = _upsert_knowledge_mapping(db, 1, 10, 20, "auto_list_evidence", 2)

    assert result == existing
    assert result.source == "user_reject"
    assert result.support_count == 7


def test_upsert_knowledge_mapping_preserves_auto_support_source():
    db = MagicMock()
    existing = MagicMock()
    existing.source = "auto_support"
    existing.is_validated = True
    db.query.return_value.filter.return_value.first.return_value = existing
    existing.support_count = 5

    result = _upsert_knowledge_mapping(db, 1, 10, 20, "auto_list_evidence", 1)

    assert result.source == "auto_support"
    assert result.support_count == 6


def test_upsert_knowledge_mapping_updates_non_protected_source():
    db = MagicMock()
    existing = MagicMock()
    existing.source = "auto_list_evidence"
    existing.is_validated = False
    db.query.return_value.filter.return_value.first.return_value = existing
    existing.support_count = 5

    result = _upsert_knowledge_mapping(db, 1, 10, 20, "auto_qwen", 1)

    assert result == existing
    assert result.source == "auto_qwen"
    assert result.support_count == 6
