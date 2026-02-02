"""
Brand recognition module refactored into logical components.

This module provides functionality for extracting, validating, and normalizing
brand and product entities from text using a combination of rule-based methods
and LLM-based approaches.
"""

from services.brand_recognition.models import (
    EntityCandidate,
    ExtractedEntities,
    ExtractionDebugInfo,
    ExtractionResult,
    ExtractionQuality,
)
from services.brand_recognition.orchestrator import (
    extract_entities,
    canonicalize_entities,
)
from services.brand_recognition.candidate_generator import generate_candidates
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    classify_entity_type,
    _has_product_model_patterns,
    _has_product_suffix,
)
from services.brand_recognition.brand_extractor import (
    _has_brand_patterns,
    _has_product_patterns,
    _calculate_brand_confidence,
    _calculate_product_confidence,
    _extract_entities_with_qwen,
    _parse_extraction_response,
    _build_extraction_system_prompt,
    _build_extraction_prompt,
)
from services.brand_recognition.entity_validator import (
    _filter_candidates_simple,
    _filter_candidates_with_qwen,
    _verify_entity_with_qwen,
)
from services.brand_recognition.brand_extractor import (
    _check_wikidata_brand,
    _check_wikidata_product,
)
from services.brand_recognition.clustering import (
    _simple_clustering,
    _cluster_with_embeddings,
    _llm_assisted_clustering,
    _split_clusters_by_type,
)
from services.brand_recognition.candidate_generator import (
    _regex_candidates,
    _default_alias_table,
    _alias_hits,
    _list_table_candidates,
)
from constants import GENERIC_TERMS, KNOWN_PRODUCTS, PRODUCT_HINTS
from services.brand_recognition.text_utils import (
    normalize_text_for_ner,
    extract_snippet_for_brand,
    extract_snippet_with_list_awareness,
    _truncate_list_item,
    _build_alias_lookup,
    _has_variant_signals,
    _match_substring_alias,
    _extract_evidence,
    _parse_json_response,
)
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
    extract_primary_entities_from_list_item,
    parse_expected_count,
    get_list_item_count,
)
from services.brand_recognition.config import (
    ENABLE_QWEN_FILTERING,
    ENABLE_QWEN_EXTRACTION,
    ENABLE_EMBEDDING_CLUSTERING,
    ENABLE_LLM_CLUSTERING,
    ENABLE_WIKIDATA_NORMALIZATION,
    ENABLE_BRAND_VALIDATION,
    ENABLE_CONFIDENCE_VERIFICATION,
    AMBIGUOUS_CONFIDENCE_THRESHOLD,
    OLLAMA_EMBEDDING_MODEL,
)

__all__ = [
    # Data models
    "EntityCandidate",
    "ExtractedEntities",
    "ExtractionDebugInfo",
    "ExtractionResult",
    "ExtractionQuality",

    # Main API functions
    "extract_entities",
    "canonicalize_entities",
    "generate_candidates",

    # Classification functions
    "is_likely_brand",
    "is_likely_product",
    "classify_entity_type",
    "_has_product_model_patterns",
    "_has_product_suffix",
    "_has_brand_patterns",
    "_has_product_patterns",
    "_calculate_brand_confidence",
    "_calculate_product_confidence",

    # Text utilities
    "normalize_text_for_ner",
    "extract_snippet_for_brand",
    "extract_snippet_with_list_awareness",
    "_truncate_list_item",

    # List processing
    "is_list_format",
    "split_into_list_items",
    "extract_primary_entities_from_list_item",
    "parse_expected_count",
    "get_list_item_count",

    # Configuration
    "ENABLE_QWEN_FILTERING",
    "ENABLE_QWEN_EXTRACTION",
    "ENABLE_EMBEDDING_CLUSTERING",
    "ENABLE_LLM_CLUSTERING",
    "ENABLE_WIKIDATA_NORMALIZATION",
    "ENABLE_BRAND_VALIDATION",
    "ENABLE_CONFIDENCE_VERIFICATION",
    "AMBIGUOUS_CONFIDENCE_THRESHOLD",
    "OLLAMA_EMBEDDING_MODEL",
]
