"""
Main orchestration for brand recognition pipeline.

This module coordinates the overall entity extraction pipeline, bringing together
all the specialized modules for candidate generation, extraction, validation,
normalization, and clustering.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from services.brand_recognition.models import (
    EntityCandidate,
    ExtractionResult,
    ExtractionQuality,
)
from services.brand_recognition.config import (
    ENABLE_QWEN_EXTRACTION,
    ENABLE_QWEN_FILTERING,
    ENABLE_EMBEDDING_CLUSTERING,
    ENABLE_LLM_CLUSTERING,
)
from services.brand_recognition.async_utils import _run_async
from services.brand_recognition.text_utils import normalize_text_for_ner

logger = logging.getLogger(__name__)


def extract_entities(
    text: str,
    primary_brand: str,
    aliases: Dict[str, List[str]],
    vertical: str = "",
    vertical_description: str = "",
    db: Optional[Session] = None,
    vertical_id: Optional[int] = None,
) -> ExtractionResult:
    """
    Main entry point for entity extraction.

    This function orchestrates the entire entity extraction pipeline:
    1. Parse expected count from text
    2. Candidate generation
    3. Qwen-based extraction (if enabled) with expected count hint
    4. Retry if extracted count < expected count
    5. Filtering and validation
    6. Normalization and clustering
    7. Final result assembly with quality assessment
    """
    # Import here to avoid circular imports
    from services.brand_recognition.candidate_generator import generate_candidates
    from services.brand_recognition.brand_extractor import _extract_entities_with_qwen
    from services.brand_recognition.list_processor import (
        parse_expected_count,
        get_list_item_count,
    )

    if ENABLE_QWEN_EXTRACTION:
        # Step 1: Parse expected count
        expected_count = parse_expected_count(text)
        list_item_count = get_list_item_count(text)
        min_expected = expected_count or list_item_count or None

        # Step 2: First extraction attempt with min_expected hint
        result = _run_async(_extract_entities_with_qwen(
            text, vertical, vertical_description, db=db, vertical_id=vertical_id,
            min_expected_entities=min_expected,
        ))

        # Step 3: Check if extraction is sufficient and retry if needed
        extracted_count = len(result.brands) + len(result.products)
        if min_expected and extracted_count < min_expected:
            logger.info(
                f"[Extraction] Insufficient: extracted {extracted_count}, "
                f"expected at least {min_expected}. Retrying..."
            )
            retry_feedback = (
                f"Previous extraction found only {extracted_count} entities. "
                f"The text mentions {min_expected} items. Please extract at least "
                f"{min_expected} brand/product entities."
            )
            result = _run_async(_extract_entities_with_qwen(
                text, vertical, vertical_description, db=db, vertical_id=vertical_id,
                min_expected_entities=min_expected,
                retry_feedback=retry_feedback,
            ))

        # Step 4: Final quality assessment
        result.quality = _assess_extraction_quality(
            text, result, expected_count, list_item_count
        )
        return result

    normalized_text = normalize_text_for_ner(text)
    candidates = generate_candidates(normalized_text, primary_brand, aliases)

    if ENABLE_QWEN_FILTERING:
        from services.brand_recognition.entity_validator import _filter_candidates_with_qwen
        filtered_candidates = _run_async(
            _filter_candidates_with_qwen(candidates, normalized_text, vertical, vertical_description)
        )
    else:
        from services.brand_recognition.entity_validator import _filter_candidates_simple
        filtered_candidates = _filter_candidates_simple(candidates)

    from services.brand_recognition.list_processor import _filter_by_list_position
    filtered_candidates = _filter_by_list_position(filtered_candidates, text)

    if ENABLE_EMBEDDING_CLUSTERING:
        from services.brand_recognition.clustering import _cluster_with_embeddings
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        from services.brand_recognition.clustering import _llm_assisted_clustering
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        from services.brand_recognition.clustering import _simple_clustering
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    from services.brand_recognition.clustering import _split_clusters_by_type
    brands, products = _split_clusters_by_type(final_clusters, filtered_candidates)
    
    return ExtractionResult(brands=brands, products=products)


def canonicalize_entities(
    candidates: List[EntityCandidate],
    primary_brand: str,
    aliases: Dict[str, List[str]],
    alias_table: Dict[str, str] | None = None,
    text: str = "",
) -> Dict[str, List[str]]:
    """
    Canonicalize entities by filtering and clustering.
    
    This is a simplified version of the extraction pipeline focused on
    canonicalizing already-extracted entities.
    """
    from services.brand_recognition.config import (
        ENABLE_QWEN_FILTERING,
        ENABLE_EMBEDDING_CLUSTERING,
        ENABLE_LLM_CLUSTERING,
    )
    from services.brand_recognition.entity_validator import (
        _filter_candidates_with_qwen,
        _filter_candidates_simple,
    )
    from services.brand_recognition.clustering import (
        _cluster_with_embeddings,
        _llm_assisted_clustering,
        _simple_clustering,
    )
    from services.brand_recognition.async_utils import _run_async
    
    if ENABLE_QWEN_FILTERING and text:
        filtered_candidates = _run_async(_filter_candidates_with_qwen(candidates, text))
    else:
        filtered_candidates = _filter_candidates_simple(candidates)

    if ENABLE_EMBEDDING_CLUSTERING:
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    return final_clusters


def _assess_extraction_quality(
    text: str,
    result: ExtractionResult,
    expected_count: Optional[int],
    list_item_count: int,
) -> ExtractionQuality:
    """Assess extraction quality based on expected vs actual counts."""
    extracted_count = len(result.brands) + len(result.products)
    min_expected = expected_count or list_item_count or None

    is_sufficient = True
    warning_message = None

    if min_expected and extracted_count < min_expected:
        is_sufficient = False
        warning_message = (
            f"Extracted {extracted_count} entities but expected at least {min_expected}"
        )

    return ExtractionQuality(
        expected_count=expected_count,
        list_item_count=list_item_count,
        extracted_count=extracted_count,
        is_sufficient=is_sufficient,
        warning_message=warning_message,
    )
