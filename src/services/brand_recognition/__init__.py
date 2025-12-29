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
)
from services.brand_recognition.text_utils import normalize_text_for_ner
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
    extract_primary_entities_from_list_item,
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
    
    # Main API functions
    "extract_entities",
    "canonicalize_entities",
    "generate_candidates",
    
    # Classification functions
    "is_likely_brand",
    "is_likely_product",
    "classify_entity_type",
    
    # Text utilities
    "normalize_text_for_ner",
    
    # List processing
    "is_list_format",
    "split_into_list_items",
    "extract_primary_entities_from_list_item",
    
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
