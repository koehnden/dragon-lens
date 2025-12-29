"""
Main entry point for brand recognition.

This module provides the public API for brand recognition, delegating to
specialized modules in the brand_recognition package.
"""

import logging
from typing import Dict, List

from services.brand_recognition.models import (
    EntityCandidate,
    ExtractionResult,
    ExtractionDebugInfo,
    ExtractedEntities,
)
from services.brand_recognition.orchestrator import (
    extract_entities as _extract_entities,
    canonicalize_entities as _canonicalize_entities,
)
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    classify_entity_type,
)
from services.brand_recognition.text_utils import normalize_text_for_ner
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
    extract_primary_entities_from_list_item,
)
from services.brand_recognition.config import (
    ENABLE_QWEN_EXTRACTION,
    ENABLE_QWEN_FILTERING,
    ENABLE_EMBEDDING_CLUSTERING,
    ENABLE_LLM_CLUSTERING,
    ENABLE_WIKIDATA_NORMALIZATION,
    ENABLE_BRAND_VALIDATION,
    ENABLE_CONFIDENCE_VERIFICATION,
    OLLAMA_EMBEDDING_MODEL,
    AMBIGUOUS_CONFIDENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)


# Re-export public functions
extract_entities = _extract_entities
canonicalize_entities = _canonicalize_entities


def extract_snippet_for_brand(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: List[tuple],
    max_length: int = 50,
) -> str:
    """Extract a snippet of text containing a brand mention."""
    if not text:
        return ""

    snippet_start = brand_start
    snippet_end = min(len(text), brand_end + max_length)

    for other_start, other_end in all_brand_positions:
        if other_start > brand_end and other_start < snippet_end:
            snippet_end = other_start
            break

    return text[snippet_start:snippet_end].strip()


def extract_snippet_with_list_awareness(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: List[tuple],
    brand_names_lower: List[str],
    max_length: int = 50,
) -> str:
    """Extract a snippet with awareness of list formatting."""
    if is_list_format(text):
        list_items = split_into_list_items(text)
        list_items_lower = [item.lower() for item in list_items]
        for i, item_lower in enumerate(list_items_lower):
            for name in brand_names_lower:
                if name in item_lower:
                    return list_items[i]

    return extract_snippet_for_brand(
        text, brand_start, brand_end, all_brand_positions, max_length
    )


# Re-export constants for backward compatibility
__all__ = [
    "EntityCandidate",
    "ExtractionResult",
    "ExtractionDebugInfo",
    "ExtractedEntities",
    "extract_entities",
    "canonicalize_entities",
    "is_likely_brand",
    "is_likely_product",
    "classify_entity_type",
    "normalize_text_for_ner",
    "is_list_format",
    "split_into_list_items",
    "extract_primary_entities_from_list_item",
    "extract_snippet_for_brand",
    "extract_snippet_with_list_awareness",
    "ENABLE_QWEN_EXTRACTION",
    "ENABLE_QWEN_FILTERING",
    "ENABLE_EMBEDDING_CLUSTERING",
    "ENABLE_LLM_CLUSTERING",
    "ENABLE_WIKIDATA_NORMALIZATION",
    "ENABLE_BRAND_VALIDATION",
    "ENABLE_CONFIDENCE_VERIFICATION",
    "OLLAMA_EMBEDDING_MODEL",
    "AMBIGUOUS_CONFIDENCE_THRESHOLD",
]
