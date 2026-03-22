"""Data models for the new extraction pipeline."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BrandProductPair:
    """One extracted brand/product pair inside an item."""

    brand: Optional[str] = None
    product: Optional[str] = None
    brand_source: str = ""
    product_source: str = ""


@dataclass
class ResponseItem:
    """A single item parsed from a response (list item, table row, paragraph)."""

    text: str
    position: int
    response_id: Optional[str] = None


@dataclass
class ItemExtractionResult:
    """Extraction result for a single item."""

    item: ResponseItem
    pairs: list[BrandProductPair] = field(default_factory=list)

    @property
    def brand(self) -> Optional[str]:
        for pair in self.pairs:
            if pair.brand:
                return pair.brand
        return None

    @property
    def product(self) -> Optional[str]:
        for pair in self.pairs:
            if pair.product:
                return pair.product
        return None

    @property
    def brand_source(self) -> str:
        for pair in self.pairs:
            if pair.brand_source:
                return pair.brand_source
        return ""

    @property
    def product_source(self) -> str:
        for pair in self.pairs:
            if pair.product_source:
                return pair.product_source
        return ""


@dataclass
class BatchExtractionResult:
    """Result for all items from one or more responses."""

    items: list[ItemExtractionResult] = field(default_factory=list)
    response_results: dict[str, dict] = field(default_factory=dict)
    brand_aliases: dict[str, str] = field(default_factory=dict)
    product_aliases: dict[str, str] = field(default_factory=dict)
    product_brand_map: dict[str, str] = field(default_factory=dict)
    validated_brands: set[str] = field(default_factory=set)
    validated_products: set[str] = field(default_factory=set)
    rejected_brands: set[str] = field(default_factory=set)
    rejected_products: set[str] = field(default_factory=set)


@dataclass
class PipelineDebugInfo:
    """Debug info for the entire pipeline run."""

    step0_item_count: int = 0
    step0_response_count: int = 0
    step1_kb_matched_brands: list[str] = field(default_factory=list)
    step1_kb_matched_products: list[str] = field(default_factory=list)
    step2_qwen_input_count: int = 0
    step2_qwen_batch_count: int = 0
    step2_qwen_extracted_brands: list[str] = field(default_factory=list)
    step2_qwen_extracted_products: list[str] = field(default_factory=list)
    step3_normalized_brands: dict[str, str] = field(default_factory=dict)
    step3_normalized_products: dict[str, str] = field(default_factory=dict)
    step3_product_brand_map: dict[str, str] = field(default_factory=dict)
    step3_rejected_brands: list[str] = field(default_factory=list)
    step3_rejected_products: list[str] = field(default_factory=list)
    knowledge_seeded: bool = False
    remote_llm_call_count: int = 0
