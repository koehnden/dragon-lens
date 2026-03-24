"""
Main orchestration for brand recognition pipeline.

This module coordinates the overall entity extraction pipeline.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from services.brand_recognition.models import (
    ExtractionResult,
    ExtractionQuality,
)
from services.brand_recognition.async_utils import _run_async

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

    The redesigned pipeline is run-scoped. This wrapper executes the run-level
    pipeline against a single response for direct callers that still need a
    one-shot extraction.
    """
    from services.extraction.pipeline import ExtractionPipeline
    from services.brand_recognition.list_processor import (
        parse_expected_count,
        get_list_item_count,
    )

    expected_count = parse_expected_count(text)
    list_item_count = get_list_item_count(text)
    pipeline = ExtractionPipeline(
        vertical=vertical or "generic",
        vertical_description=vertical_description or "",
        db=db,
    )
    user_brands = []
    if primary_brand:
        user_brands.append(
            {
                "display_name": primary_brand,
                "aliases": aliases or {"zh": [], "en": []},
            }
        )

    try:
        logger.info(f"[ORCHESTRATOR] Calling pipeline.process_response()")
        _run_async(
            pipeline.process_response(
                text,
                response_id="single-response",
                user_brands=user_brands,
            )
        )
        logger.info(f"[ORCHESTRATOR] process_response completed, calling finalize()")
        batch = _run_async(pipeline.finalize())
        logger.info(f"[ORCHESTRATOR] finalize completed")
        result = batch.response_results.get("single-response", ExtractionResult(brands={}, products={}))
        result.quality = _assess_extraction_quality(
            text, result, expected_count, list_item_count
        )
        return result
    finally:
        pipeline.close()


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
