"""
Data models for brand recognition.

This module contains the core data structures used throughout the brand recognition
pipeline, including entity candidates, extraction results, and debug information.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class EntityCandidate:
    """Represents a candidate entity extracted from text."""
    name: str
    source: str
    entity_type: str = "unknown"


@dataclass
class ExtractedEntities:
    """Represents primary entities extracted from a list item."""
    primary_brand: Optional[str]
    primary_product: Optional[str]
    brand_confidence: float = 0.0
    product_confidence: float = 0.0


@dataclass
class ExtractionDebugInfo:
    """Debug information for entity extraction pipeline."""
    raw_brands: List[str]
    raw_products: List[str]
    rejected_at_normalization: List[dict]
    rejected_at_validation: List[str]
    rejected_at_list_filter: List[str]
    final_brands: List[str]
    final_products: List[str]


@dataclass
class ExtractionResult:
    """Final result of entity extraction."""
    brands: Dict[str, List[str]]
    products: Dict[str, List[str]]
    debug_info: Optional[ExtractionDebugInfo] = None

    def all_entities(self) -> Dict[str, List[str]]:
        """Combine brands and products into a single dictionary."""
        combined = dict(self.brands)
        combined.update(self.products)
        return combined
