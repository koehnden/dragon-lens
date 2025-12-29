"""
Brand extraction using Qwen.

This module contains functions for extracting entities using Qwen-based
extraction with structured prompts.
"""

import logging
from typing import Dict, List

from services.brand_recognition.models import ExtractionResult

logger = logging.getLogger(__name__)


async def _extract_entities_with_qwen(
    text: str,
    vertical: str = "",
    vertical_description: str = "",
) -> ExtractionResult:
    """Extract entities using Qwen-based extraction."""
    # Simplified version - in real implementation this would call Qwen
    # For now, return empty result
    return ExtractionResult(brands={}, products={})
