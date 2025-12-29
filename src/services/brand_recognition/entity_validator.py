"""
Entity validation and filtering.

This module contains functions for validating and filtering entity candidates
using Qwen-based validation and simple rule-based filtering.
"""

import logging
from typing import Dict, List

from services.brand_recognition.models import EntityCandidate
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    classify_entity_type,
)

logger = logging.getLogger(__name__)


async def _filter_candidates_with_qwen(
    candidates: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = "",
) -> List[EntityCandidate]:
    """Filter candidates using Qwen-based validation."""
    # Simplified version - in real implementation this would call Qwen
    # For now, just use simple filtering
    return _filter_candidates_simple(candidates)


def _filter_candidates_simple(candidates: List[EntityCandidate]) -> List[EntityCandidate]:
    """Filter candidates using simple rule-based validation."""
    filtered = []
    for candidate in candidates:
        entity_type = classify_entity_type(candidate.name)
        if entity_type in ["brand", "product"]:
            candidate.entity_type = entity_type
            filtered.append(candidate)
    return filtered
