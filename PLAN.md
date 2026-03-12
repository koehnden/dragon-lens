# Extraction Redesign: Implementation Plan

## Goal
Replace the current brand/product extraction pipeline with a new approach:
0. **Seed vertical** from user brands + DeepSeek (cold start, once per vertical)
1. **Rule-based extraction** from knowledge base (per item)
2. **Qwen LLM extraction** for items with missing brand/product (batched, max 10)
3. **DeepSeek consultation** for normalization, mapping, and validation (batched)

The rest of the system (mentions, metrics, sentiment, UI, consolidation DB writes) stays untouched.

---

## Architecture Overview

```
Vertical Created / First Run
      |
[Step -1: Seed] (if < 10 validated brands in KB)
      |  Insert user-provided brands + aliases (validated=True, source="user")
      |  Call DeepSeek for top 30-50 brands + products + aliases for vertical
      |  Insert as validated=False, source="seed"
      |  -> KB now populated for Step 1
      |
Response Text (original Chinese answer_zh)
      |
[Step 0] Parse into structured items
      |  split_into_list_items() / extract_markdown_table_row_items()
      |  -> list[ResponseItem(text, position, response_id)]
      |
[Step 1] Rule-based extraction (per item)
      |  KnowledgeBaseMatcher: load KB brands/products/aliases for vertical
      |  -> for each item: match known brands+aliases, known products+aliases
      |  -> ItemExtractionResult(brand=..., product=..., source="kb")
      |  -> collect items where brand is None or product is None
      |
[Step 2] Qwen batch extraction (for missing items only)
      |  Group missing items by response (all items from one response together)
      |  Batch up to 10 items per Qwen call, include intro/header context
      |  -> fill in missing brands/products
      |  -> add newly found entities to in-memory "session KB" for subsequent items
      |
[Step 3] DeepSeek consultation (per run, after all responses processed)
      |  3a. Normalize brands + map products to brands (single call per batch)
      |  3b. Validate relevance to vertical (separate call per batch)
      |  -> store validated entities, aliases, mappings in knowledge DB (TursoDB)
      |
      v
ExtractionResult (same shape as today -> plugs into existing pipeline)
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/services/extraction/__init__.py` | Package init, re-export public API |
| `src/services/extraction/models.py` | Data classes: ResponseItem, ItemExtractionResult, etc. |
| `src/services/extraction/vertical_seeder.py` | Step -1: Cold start seeding from user brands + DeepSeek |
| `src/services/extraction/item_parser.py` | Step 0: Parse responses into items |
| `src/services/extraction/rule_extractor.py` | Step 1: KB-based rule matching |
| `src/services/extraction/qwen_extractor.py` | Step 2: Qwen batch extraction |
| `src/services/extraction/deepseek_consultant.py` | Step 3: DeepSeek normalization/validation |
| `src/services/extraction/pipeline.py` | Orchestrate steps -1 through 3, produce ExtractionResult |
| `src/prompts/extraction/deepseek_seed_vertical.md` | New prompt: generate brands/products for vertical |
| `src/prompts/extraction/qwen_item_extraction.md` | New prompt: extract brand/product from list items |
| `src/prompts/extraction/deepseek_normalize_map.md` | New prompt: normalize + map brands/products |
| `src/prompts/extraction/deepseek_validate.md` | New prompt: validate relevance to vertical |
| `tests/unit/test_vertical_seeder.py` | Unit tests for cold start seeding |
| `tests/unit/test_item_parser.py` | Unit tests for item parsing |
| `tests/unit/test_rule_extractor.py` | Unit tests for KB matching |
| `tests/unit/test_qwen_extractor.py` | Unit tests for Qwen batch extraction |
| `tests/unit/test_deepseek_consultant.py` | Unit tests for DeepSeek consultation |
| `tests/unit/test_extraction_pipeline.py` | Unit tests for full pipeline |
| `tests/integration/test_extraction_e2e.py` | E2E test using suv_example_mini fixture |

## Files to Modify

| File | Change |
|------|--------|
| `src/services/brand_recognition/orchestrator.py` | `extract_entities()` delegates to new pipeline |
| `src/services/brand_recognition/__init__.py` | Update imports if needed |
| `src/models/knowledge_domain.py` | Add `alias_key` columns, add `KnowledgeExtractionLog` |

## Schema Changes (TursoDB / knowledge_domain.py)

### Add `alias_key` indexed column to 5 tables

The rule extractor (Step 1) needs fast lookups. Currently every query uses
`func.lower(canonical_name)` at query time. Adding a pre-computed, indexed
`alias_key` column (populated via `normalize_entity_key()` on insert) enables
efficient bulk loading of the entire vertical's KB into memory.

Tables that get `alias_key`:
- `knowledge_brands` — indexed, populated from `canonical_name`
- `knowledge_brand_aliases` — indexed, populated from `alias`
- `knowledge_products` — indexed, populated from `canonical_name`
- `knowledge_product_aliases` — indexed, populated from `alias`
- `knowledge_rejected_entities` — indexed, populated from `name`

```python
# Example for knowledge_brands:
alias_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
# Set on insert: alias_key = normalize_entity_key(canonical_name)
```

### Add `KnowledgeExtractionLog` table (new)

Audit trail for every entity extracted by the pipeline. Essential for debugging
and iteratively improving the KB.

```python
class KnowledgeExtractionLog(KnowledgeBase):
    __tablename__ = "knowledge_extraction_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    extraction_source: Mapped[str] = mapped_column(String(50), nullable=False)
    # "kb_rule", "qwen_batch", "deepseek_normalize", "deepseek_validate", "seed", "user_feedback"
    resolved_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    was_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    item_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

### Tables kept as-is

- `knowledge_verticals` — no changes
- `knowledge_vertical_aliases` — no changes
- `knowledge_product_brand_mappings` — kept as audit trail (Step 3 writes here with source)
- `knowledge_feedback_events` — no changes (independent of extraction)
- `knowledge_translation_overrides` — no changes (independent of extraction)

## Files NOT Modified (kept as-is)

Everything outside `brand_recognition/orchestrator.py` stays untouched:
- `workers/pipeline.py` (calls `extract_entities()` which we preserve)
- `brand_discovery.py` (calls `extract_entities()` which we preserve)
- `entity_consolidation.py` (run-level consolidation, untouched)
- `consolidation_service.py` (enhanced consolidation, untouched)
- All mention/metric/sentiment/translation code

---

## Step-by-Step Implementation

### Phase 1: Data Models, Schema Changes & Cold Start Seeder

#### 1.1 `src/services/extraction/models.py`

```python
@dataclass
class ResponseItem:
    """A single item parsed from a response (list item, table row, paragraph)."""
    text: str               # The item text
    position: int           # 0-indexed position in the response
    response_id: str | None # Optional: link back to the answer

@dataclass
class ItemExtractionResult:
    """Extraction result for a single item."""
    item: ResponseItem
    brand: str | None
    product: str | None
    brand_source: str       # "kb", "qwen", "proximity", "deepseek"
    product_source: str     # "kb", "qwen", "proximity", "deepseek"

@dataclass
class BatchExtractionResult:
    """Result for all items from one or more responses."""
    items: list[ItemExtractionResult]
    # Brand normalization: alias -> canonical
    brand_aliases: dict[str, str]
    # Product-brand mapping: product -> brand
    product_brand_map: dict[str, str]
    # Entities validated as relevant to vertical
    validated_brands: set[str]
    validated_products: set[str]
    # Entities rejected as irrelevant
    rejected_brands: set[str]
    rejected_products: set[str]

@dataclass
class PipelineDebugInfo:
    """Debug info for the entire pipeline run."""
    step0_item_count: int
    step1_kb_matched_brands: list[str]
    step1_kb_matched_products: list[str]
    step2_qwen_input_count: int
    step2_qwen_extracted_brands: list[str]
    step2_qwen_extracted_products: list[str]
    step3_normalized_brands: dict[str, str]
    step3_product_brand_map: dict[str, str]
    step3_rejected_brands: list[str]
    step3_rejected_products: list[str]
```

#### 1.2 Schema changes in `src/models/knowledge_domain.py`

Add `alias_key` columns to 5 tables (see Schema Changes section above).
Add `KnowledgeExtractionLog` model.

Run `alembic revision --autogenerate -m "add alias_key columns and extraction log"`
to generate the migration, then verify and apply.

For existing data, backfill `alias_key` via a data migration step:
```python
# In the migration:
from services.canonicalization_metrics import normalize_entity_key
# For each row in knowledge_brands: alias_key = normalize_entity_key(canonical_name)
# Same for brand_aliases, products, product_aliases, rejected_entities
```

#### 1.3 `src/services/extraction/vertical_seeder.py`

Solves the cold start problem: on first run for a vertical (< 10 validated
brands in KB), seed the knowledge base with known entities.

```python
class VerticalSeeder:
    """Seed a vertical's knowledge base for cold start."""

    def __init__(self, vertical: str, vertical_description: str, vertical_id: int):
        self.vertical = vertical
        self.vertical_description = vertical_description
        self.vertical_id = vertical_id

    async def should_seed(self, db: Session) -> bool:
        """Check if vertical needs seeding (< 10 validated brands)."""
        # Count KnowledgeBrand WHERE vertical_id=X AND is_validated=True
        # Return True if count < 10

    def seed_from_user_brands(self, db: Session, user_brands: list[Brand]) -> int:
        """Insert user-provided brands + aliases as validated.

        Reads aliases from Brand.aliases dict ({"zh": [...], "en": [...]}).
        Creates KnowledgeBrand (is_validated=True, source="user") +
        KnowledgeBrandAlias for each alias.
        Returns count of brands seeded.
        """

    async def seed_from_deepseek(self, db: Session) -> int:
        """Ask DeepSeek for top brands/products for this vertical.

        One DeepSeek call returns:
        {
          "brands": [
            {
              "name_en": "Toyota",
              "name_zh": "丰田",
              "aliases": ["一汽丰田", "广汽丰田"],
              "products": [
                {"name": "RAV4", "aliases": ["RAV4荣放", "荣放"]},
                {"name": "Camry", "aliases": ["凯美瑞"]}
              ]
            }
          ]
        }

        Stores everything with is_validated=False, source="seed".
        Creates:
        - KnowledgeBrand + KnowledgeBrandAlias (Chinese aliases are key!)
        - KnowledgeProduct + KnowledgeProductAlias
        - KnowledgeProductBrandMapping (source="seed")
        Returns count of brands seeded.
        """

    async def ensure_seeded(self, db: Session, user_brands: list[Brand] | None = None):
        """Main entry point: seed if needed, skip if already seeded.

        Order:
        1. Insert user brands first (these are ground truth, validated=True)
        2. If still < 10 validated, call DeepSeek for market knowledge
        3. DeepSeek results stored as unvalidated seeds
        """
```

**Seeding rules:**
- User brands: `is_validated=True`, `validation_source="user"` — ground truth
- DeepSeek seeds: `is_validated=False`, `validation_source="seed"` — provisional
- Seed runs once per vertical, triggered by `ensure_seeded()` in pipeline
- Seeded entities participate in Step 1 rule matching immediately
- Over time, validated via mention count, Step 3 validation, or user feedback

#### 1.4 `src/prompts/extraction/deepseek_seed_vertical.md`

```markdown
---
id: deepseek_seed_vertical
version: v1
requires:
  - vertical
  - vertical_description
---
You are a market research expert for the Chinese consumer market.

For the following industry vertical:
Vertical: {{ vertical }}
Description: {{ vertical_description }}

List the top 30-50 brands and their key products that a Chinese consumer
would likely encounter or ask about in this vertical.

IMPORTANT:
- Include BOTH Chinese names (name_zh) and English names (name_en)
- Include Chinese aliases: JV names (一汽丰田, 广汽丰田), colloquial names, etc.
- Include product aliases: Chinese names (凯美瑞 for Camry), model variants
- Focus on brands/products that appear in Chinese LLM responses
- Cover mainstream, premium, and budget segments

OUTPUT (JSON only):
{
  "brands": [
    {
      "name_en": "Toyota",
      "name_zh": "丰田",
      "aliases": ["一汽丰田", "广汽丰田", "TOYOTA"],
      "products": [
        {"name": "RAV4", "aliases": ["RAV4荣放", "荣放"]},
        {"name": "Camry", "aliases": ["凯美瑞"]},
        {"name": "Highlander", "aliases": ["汉兰达"]}
      ]
    }
  ]
}
```

**Tests** (`tests/unit/test_vertical_seeder.py`):
- `should_seed()`: returns True when < 10 validated brands
- `should_seed()`: returns False when >= 10 validated brands
- `seed_from_user_brands()`: creates KnowledgeBrand + aliases with validated=True
- `seed_from_user_brands()`: skips duplicates if brand already exists
- `seed_from_deepseek()`: mock DeepSeek, verify brands/products/aliases created
- `seed_from_deepseek()`: all entries have is_validated=False, source="seed"
- `seed_from_deepseek()`: product-brand mappings created with source="seed"
- `seed_from_deepseek()`: Chinese aliases stored correctly
- `seed_from_deepseek()`: graceful fallback if no DeepSeek API key
- `ensure_seeded()`: calls seed_from_user_brands then seed_from_deepseek
- `ensure_seeded()`: skips DeepSeek if user brands already >= 10

### Phase 2: Item Parser (Step 0)

#### 2.1 `src/services/extraction/item_parser.py`

Reuse existing `split_into_list_items()` and `extract_markdown_table_row_items()` from `list_processor.py`. Wrap them:

```python
def parse_response_into_items(text: str, response_id: str | None = None) -> list[ResponseItem]:
    """Parse a response into structured items."""
    # 1. Try list detection (reuse list_processor.is_list_format / split_into_list_items)
    # 2. Try table detection (reuse markdown_table functions)
    # 3. Fallback: treat entire text as one item
    # Returns list[ResponseItem]

def extract_intro_context(text: str) -> str | None:
    """Extract intro/header text before the first list item."""
    # Reuse _get_intro_text() and _get_header_context_text() from list_processor
```

**Tests** (`tests/unit/test_item_parser.py`):
- Numbered list -> correct item count and text
- Bullet list -> correct items
- Markdown table -> rows as items
- Mixed format -> correct handling
- No list structure -> single item
- Intro text extraction
- Chinese numbered lists (1、2、3、)

### Phase 3: Rule-Based Extractor (Step 1)

#### 3.1 `src/services/extraction/rule_extractor.py`

```python
class KnowledgeBaseMatcher:
    """Fast rule-based entity matcher using knowledge base."""

    def __init__(self, vertical_id: int, db: Session | None = None):
        # Load from knowledge DB:
        # - All KnowledgeBrand + KnowledgeBrandAlias for this vertical
        # - All KnowledgeProduct + KnowledgeProductAlias for this vertical
        # - All KnowledgeRejectedEntity for this vertical
        # Build lookup dicts for fast matching
        self._brand_lookup: dict[str, str] = {}   # lowered alias -> canonical
        self._product_lookup: dict[str, str] = {}  # lowered alias -> canonical
        self._rejected: set[str] = set()

    def match_item(self, item: ResponseItem) -> ItemExtractionResult:
        """Match a single item against the knowledge base."""
        # 1. Search item text for known brands (longest match first)
        # 2. Search item text for known products (longest match first)
        # 3. Skip rejected entities
        # Returns ItemExtractionResult with source="kb"

    def add_to_session(self, brand: str | None, product: str | None):
        """Add newly discovered entity to in-memory session KB."""
        # Called after Qwen extraction to enable matching in subsequent items

    @staticmethod
    def _build_lookup(entities: list, aliases: list) -> dict[str, str]:
        """Build lowered-name -> canonical lookup dict."""
```

**Tests** (`tests/unit/test_rule_extractor.py`):
- Known brand in item -> extracted
- Known product in item -> extracted
- Known alias matches canonical
- Rejected entity not extracted
- Unknown entity -> None
- Session KB: after add_to_session, subsequent items match
- Multiple brands in item -> first/longest match wins
- Case-insensitive matching
- Chinese + English alias matching

### Phase 4: Qwen Batch Extractor (Step 2)

#### 4.1 `src/services/extraction/qwen_extractor.py`

```python
class QwenBatchExtractor:
    """Extract brands/products from items using Qwen, batched."""

    def __init__(self, vertical: str, vertical_description: str):
        self.vertical = vertical
        self.vertical_description = vertical_description

    async def extract_batch(
        self,
        items: list[ResponseItem],
        intro_context: str | None = None,
    ) -> list[ItemExtractionResult]:
        """Extract brand/product for up to 10 items in one Qwen call.

        Args:
            items: Items missing brand and/or product (max 10)
            intro_context: Optional intro/header text for context
        """
        # 1. Build prompt with items + context
        # 2. Call OllamaService._call_ollama() with ner_model
        # 3. Parse structured JSON response
        # 4. Map results back to items

    async def extract_missing(
        self,
        missing_items: list[tuple[ResponseItem, str | None, str | None]],
        intro_contexts: dict[str, str],
    ) -> list[ItemExtractionResult]:
        """Process all missing items, respecting batching rules.

        Rules:
        - All items from one response must be in the same batch
        - Max 10 items per batch
        - Can add items from other responses to fill up to 10
        """
        # Group by response_id
        # Build batches respecting the constraint
        # Call extract_batch for each batch
```

#### 4.2 Negative Few-Shot Examples (Feedback Loop)

The Qwen prompt is augmented with **negative examples** (previous extraction
mistakes) and **positive examples** (validated entities) from the knowledge base.
This creates an iterative learning loop:

1. **Step 3 stores rejections**: When DeepSeek rejects an entity (e.g., "SUV" is
   a generic category, not a product), it's stored in `KnowledgeRejectedEntity`
   with the reason.
2. **Step 2 loads rejections**: Before building the Qwen prompt, load the most
   recent rejections for this vertical (capped at 20 per entity type to avoid
   prompt bloat).
3. **Prompt includes negative examples**: "DO NOT extract these — they were
   incorrectly identified before: SUV (generic category), 新能源车 (generic
   category), 比亚迪 (this is a brand, not a product)".
4. **Prompt includes positive examples**: Known validated brands and products
   so Qwen knows what good extractions look like.

```python
# In QwenBatchExtractor:
def _load_augmentation(self, db: Session, vertical_id: int) -> dict:
    """Load positive/negative examples for prompt augmentation."""
    rejected = db.query(KnowledgeRejectedEntity).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id,
    ).order_by(KnowledgeRejectedEntity.created_at.desc()).limit(40).all()

    rejected_brands = [e for e in rejected if e.entity_type == EntityType.BRAND][:20]
    rejected_products = [e for e in rejected if e.entity_type == EntityType.PRODUCT][:20]

    validated_brands = db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        KnowledgeBrand.is_validated == True,
    ).limit(30).all()

    validated_products = db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        KnowledgeProduct.is_validated == True,
    ).limit(30).all()

    return {
        "rejected_brands": rejected_brands,
        "rejected_products": rejected_products,
        "validated_brands": validated_brands,
        "validated_products": validated_products,
    }
```

#### 4.3 `src/prompts/extraction/qwen_item_extraction.md`

New prompt designed for per-item extraction, with negative/positive few-shot examples:

```markdown
---
id: qwen_item_extraction
version: v1
requires:
  - vertical
  - vertical_description
  - items_json
---
You are an entity extractor for the {{ vertical }} industry.

For each numbered item below, extract the BRAND (company/manufacturer) and
PRODUCT (specific model/item) if present.

{{ intro_context_section }}

{% if validated_brands %}
KNOWN VALID BRANDS (extract these when you see them):
{% for brand in validated_brands %}
- {{ brand.display_name }}{% if brand.aliases %} (also: {{ brand.aliases | map(attribute='alias') | join(', ') }}){% endif %}
{% endfor %}
{% endif %}

{% if validated_products %}
KNOWN VALID PRODUCTS (extract these when you see them):
{% for product in validated_products %}
- {{ product.display_name }}
{% endfor %}
{% endif %}

{% if rejected_brands or rejected_products %}
DO NOT EXTRACT THESE (previous mistakes):
{% for entity in rejected_brands %}
- {{ entity.name }} — {{ entity.reason }}
{% endfor %}
{% for entity in rejected_products %}
- {{ entity.name }} — {{ entity.reason }}
{% endfor %}
{% endif %}

ITEMS TO ANALYZE:
{{ items_json }}

OUTPUT (JSON array, one entry per item):
[
  {"item_index": 0, "brand": "Toyota", "product": "RAV4"},
  {"item_index": 1, "brand": "BYD", "product": null},
  ...
]

Rules:
- brand = company/manufacturer name (e.g., Toyota, BYD, Apple)
- product = specific model/item (e.g., RAV4, 宋PLUS, iPhone 15)
- null if not found
- Extract EXACT names as they appear
- One brand and one product per item maximum
```

**Tests** (`tests/unit/test_qwen_extractor.py`):
- Mock Ollama, verify prompt construction
- Parse valid JSON response -> correct mapping
- Parse malformed response -> graceful fallback
- Batching: 15 items from 2 responses -> correct batch grouping
- Batching: all items from response A stay together
- Intro context included when available
- Empty items list -> no Ollama call
- Prompt includes validated brands/products as positive examples
- Prompt includes rejected entities as negative few-shot examples with reasons
- Negative examples capped at 20 per entity type
- No augmentation data -> prompt sections omitted cleanly

### Phase 5: DeepSeek Consultation (Step 3)

#### 5.1 `src/services/extraction/deepseek_consultant.py`

```python
class DeepSeekConsultant:
    """Consultation with DeepSeek for normalization, mapping, and validation."""

    def __init__(self, vertical: str, vertical_description: str):
        self.vertical = vertical
        self.vertical_description = vertical_description

    async def normalize_and_map(
        self,
        brands: list[str],
        products: list[str],
        item_pairs: list[tuple[str | None, str | None]],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Step 3a+3b: Normalize brands and map products to brands.

        Uses proximity (item co-occurrence) first, then DeepSeek for unmapped.

        Args:
            brands: All unique brands from steps 1+2
            products: All unique products from steps 1+2
            item_pairs: (brand, product) pairs from each item (for proximity)

        Returns:
            (brand_aliases: {alias -> canonical}, product_brand_map: {product -> brand})
        """
        # 1. Build proximity-based product-brand map from item_pairs
        # 2. Find brands that need alias normalization (duplicates, JVs)
        # 3. Find products without a brand mapping
        # 4. If anything needs DeepSeek, call it
        # 5. Merge proximity + DeepSeek results

    async def validate_relevance(
        self,
        brands: list[str],
        products: list[str],
    ) -> tuple[set[str], set[str], set[str], set[str]]:
        """Step 3c: Validate brands and products are relevant to the vertical.

        Returns:
            (valid_brands, valid_products, rejected_brands, rejected_products)
        """
        # Batch max 20 entities per call
        # Call DeepSeek to check relevance

    def store_rejections(
        self,
        db: Session,
        vertical_id: int,
        rejected_brands: set[str],
        rejected_products: set[str],
        rejection_reasons: dict[str, str],
    ) -> None:
        """Store rejected entities in KB for negative few-shot examples.

        Called after validate_relevance(). Each rejection is stored with
        the reason from DeepSeek (e.g., "generic category", "brand not product",
        "not relevant to vertical").

        These rejections are loaded by QwenBatchExtractor._load_augmentation()
        in future runs to prevent Qwen from repeating the same mistakes.
        """
        # For each rejected brand:
        #   Insert KnowledgeRejectedEntity(entity_type=BRAND, name=brand, reason=reason)
        # For each rejected product:
        #   Insert KnowledgeRejectedEntity(entity_type=PRODUCT, name=product, reason=reason)
        # Skip if already exists (idempotent)

    def _build_proximity_map(
        self,
        item_pairs: list[tuple[str | None, str | None]],
    ) -> dict[str, str]:
        """Map products to brands based on co-occurrence in same item."""

    async def _call_deepseek(self, system_prompt: str, user_prompt: str) -> str:
        """Call DeepSeek API."""
        # Use DeepSeekService from remote_llms.py
        # Falls back gracefully if no API key
```

#### 5.2 Prompts

**`src/prompts/extraction/deepseek_normalize_map.md`**:
- Input: brands list, unmapped products, vertical
- Output: `{brand_aliases: {alias: canonical}, product_brand_map: {product: brand}}`
- Instructions for JV normalization, alias deduplication (reuse rules from existing brand_normalization_prompt)

**`src/prompts/extraction/deepseek_validate.md`**:
- Input: brands + products, vertical + description
- Output: `{valid_brands: [...], valid_products: [...], rejected: [{name: "SUV", reason: "generic category"}, {name: "比亚迪", reason: "brand misclassified as product"}]}`
- Rules: reject entities not relevant to the vertical
- **Each rejection MUST include a reason** — this reason is stored in `KnowledgeRejectedEntity` and shown to Qwen as a negative few-shot example in future runs

**Tests** (`tests/unit/test_deepseek_consultant.py`):
- Proximity mapping: items with (brand, product) -> correct map
- Proximity mapping: product without brand -> unmapped
- Mock DeepSeek: normalization response parsing
- Mock DeepSeek: validation response parsing
- Mock DeepSeek: rejection reasons parsed and stored correctly
- `store_rejections()`: creates KnowledgeRejectedEntity with correct reasons
- `store_rejections()`: idempotent — skips duplicates
- `store_rejections()`: stored rejections loaded by Qwen in next run
- No DeepSeek API key -> graceful fallback (keep all, no normalization)
- Batching: >20 entities -> multiple calls

### Phase 6: Pipeline Orchestrator

#### 6.1 `src/services/extraction/pipeline.py`

```python
class ExtractionPipeline:
    """Orchestrate the 3-step extraction pipeline."""

    def __init__(
        self,
        vertical: str,
        vertical_description: str,
        vertical_id: int | None = None,
        db: Session | None = None,
    ):
        self.vertical = vertical
        self.vertical_description = vertical_description
        self.vertical_id = vertical_id
        self.db = db

    async def extract_from_response(
        self,
        text: str,
        response_id: str | None = None,
        user_brands: list[Brand] | None = None,
    ) -> ExtractionResult:
        """Extract entities from a single response.

        Runs steps -1 through 2. Step 3 (DeepSeek) runs separately via consult().
        Returns ExtractionResult compatible with existing pipeline.
        """
        # Step -1: Seed if cold start
        if self.vertical_id and self.db:
            seeder = VerticalSeeder(self.vertical, self.vertical_description, self.vertical_id)
            await seeder.ensure_seeded(self.db, user_brands)

        # Step 0: Parse items
        items = parse_response_into_items(text, response_id)
        intro = extract_intro_context(text)

        # Step 1: Rule-based extraction
        matcher = KnowledgeBaseMatcher(self.vertical_id, self.db)
        results = [matcher.match_item(item) for item in items]

        # Collect missing items
        missing = [(r.item, r.brand, r.product) for r in results
                    if r.brand is None or r.product is None]

        # Step 2: Qwen for missing items
        if missing:
            qwen = QwenBatchExtractor(self.vertical, self.vertical_description)
            qwen_results = await qwen.extract_missing(
                missing, {response_id: intro} if intro else {}
            )
            # Merge qwen results into main results
            # Add to session KB
            for qr in qwen_results:
                matcher.add_to_session(qr.brand, qr.product)

        # Convert to ExtractionResult (same shape as existing)
        return self._build_extraction_result(results)

    async def consult(
        self,
        all_results: list[ItemExtractionResult],
    ) -> BatchExtractionResult:
        """Run Step 3 (DeepSeek consultation) after all responses processed."""
        consultant = DeepSeekConsultant(self.vertical, self.vertical_description)
        # ... normalize, map, validate
        # ... store in knowledge DB

    def _build_extraction_result(
        self, item_results: list[ItemExtractionResult]
    ) -> ExtractionResult:
        """Convert item results to ExtractionResult for backward compatibility."""
        brands = {}
        products = {}
        relationships = {}
        for r in item_results:
            if r.brand:
                brands.setdefault(r.brand, [r.brand])
            if r.product:
                products.setdefault(r.product, [r.product])
            if r.brand and r.product:
                relationships[r.product] = r.brand
        return ExtractionResult(
            brands=brands,
            products=products,
            product_brand_relationships=relationships,
        )
```

#### 6.2 Wire into existing orchestrator

Modify `src/services/brand_recognition/orchestrator.py`:
- `extract_entities()` calls `ExtractionPipeline.extract_from_response()`
- Returns the same `ExtractionResult` - zero changes needed downstream

**Tests** (`tests/unit/test_extraction_pipeline.py`):
- Full pipeline with mocked KB + mocked Qwen: correct flow
- KB covers all items -> no Qwen call
- KB covers none -> all items sent to Qwen
- Mixed: some KB, some Qwen
- ExtractionResult shape matches existing format

### Phase 7: E2E Test with suv_example_mini

#### 7.1 `tests/integration/test_extraction_e2e.py`

```python
"""End-to-end extraction test using suv_example_mini.json fixture.

Tests the full pipeline: item parsing -> rule extraction -> Qwen batch ->
DeepSeek consultation -> ExtractionResult with brands/products.
"""

# Fixture: load suv_example_mini.json
# Mock Qwen with a realistic SUV response for the mini prompt
# Mock DeepSeek for normalization/validation
# Seed knowledge DB with a few known automotive brands

MOCK_LLM_RESPONSE = """
以下是预算20-30万适合二胎家庭的SUV推荐：

**5座SUV：**
1. 大众途观L - 空间宽敞，品质可靠
2. 丰田RAV4荣放 - 省油耐用，保值率高
3. 本田CR-V - 空间利用率高，动力平顺

**6座SUV：**
1. 别克昂科旗 - 2+2+2布局灵活
2. 大众揽巡 - 空间大，配置丰富
3. 奇瑞瑞虎9 - 性价比高

**7座SUV：**
1. 比亚迪唐DM-i - 油耗低，空间大
2. 理想L8 - 增程式，家庭定位
3. 丰田汉兰达 - 经典7座，空间充裕
"""

MOCK_QWEN_EXTRACTION_RESPONSE = json.dumps([
    {"item_index": 0, "brand": "大众", "product": "途观L"},
    {"item_index": 1, "brand": "丰田", "product": "RAV4荣放"},
    # ... etc
])

MOCK_DEEPSEEK_NORMALIZE_RESPONSE = json.dumps({
    "brand_aliases": {"大众": "Volkswagen", "丰田": "Toyota", ...},
    "product_brand_map": {"途观L": "Volkswagen", "RAV4荣放": "Toyota", ...},
})

def test_e2e_extraction_suv_mini(db_session, knowledge_db_session):
    """Full extraction pipeline using suv_example_mini fixture."""
    # 1. Load fixture
    # 2. Seed KB with Volkswagen brand + aliases from fixture
    # 3. Run pipeline on MOCK_LLM_RESPONSE
    # 4. Assert:
    #    - Step 0: 9 items parsed (3+3+3)
    #    - Step 1: "大众" matched from KB for items mentioning VW
    #    - Step 2: Qwen called for remaining items
    #    - Step 3: DeepSeek normalized brands
    #    - Final: ExtractionResult has expected brands/products
    #    - VW/大众 mapped to "Volkswagen" canonical
    #    - 途观L mapped to Volkswagen brand
    #    - All 9 products extracted

def test_e2e_kb_only_extraction(db_session, knowledge_db_session):
    """When KB knows all entities, no LLM calls needed."""
    # Seed KB with all brands/products from the response
    # Run pipeline -> assert zero Qwen/DeepSeek calls

def test_e2e_no_kb_extraction(db_session):
    """When KB is empty, all items go to Qwen."""
    # Empty KB -> all 9 items sent to Qwen in 1 batch (<=10)

def test_e2e_partial_kb_extraction(db_session, knowledge_db_session):
    """KB knows some brands, Qwen fills the rest."""
    # Seed KB with only VW and Toyota
    # Run pipeline -> assert Qwen called for remaining 7 items

def test_e2e_debug_info_complete(db_session, knowledge_db_session):
    """Verify debug info captures all pipeline steps."""
    # Assert PipelineDebugInfo has correct counts for each step

def test_e2e_cold_start_seeding(db_session, knowledge_db_session):
    """First run on empty vertical triggers DeepSeek seeding."""
    # Empty KB, no user brands
    # Mock DeepSeek seed response with 5 brands + products
    # Run pipeline -> assert:
    #   - DeepSeek seed called once
    #   - KnowledgeBrand entries created with source="seed", is_validated=False
    #   - Products + aliases also created
    #   - Step 1 now matches against seeded entries
    #   - Subsequent call does NOT re-seed (already populated)

def test_e2e_cold_start_with_user_brands(db_session, knowledge_db_session):
    """User brands inserted as validated, then DeepSeek fills the rest."""
    # Load suv_example_mini.json -> VW brand with aliases
    # Run pipeline -> assert:
    #   - VW brand created with is_validated=True, source="user"
    #   - VW aliases (大众汽车, 一汽-大众, 上汽大众) all in KB
    #   - DeepSeek seed called (still < 10 validated brands)
    #   - DeepSeek entries created with source="seed"
    #   - Step 1 matches VW items via user aliases AND seeded brands
```

---

## Testing Strategy Summary

| Layer | What | How | Mocking |
|-------|------|-----|---------|
| **Unit: vertical_seeder** | Cold start seeding, user brands, DeepSeek seed | Mock DeepSeek, real in-memory KB | DeepSeek mocked |
| **Unit: item_parser** | Parse lists, tables, paragraphs | Pure functions, no mocks | None |
| **Unit: rule_extractor** | KB matching, alias resolution | In-memory KB dict | No DB, no LLM |
| **Unit: qwen_extractor** | Prompt construction, response parsing, batching | Mock OllamaService._call_ollama | Ollama mocked |
| **Unit: deepseek_consultant** | Proximity mapping, response parsing, batching | Mock DeepSeekService.query | DeepSeek mocked |
| **Unit: pipeline** | Step orchestration, result assembly | Mock all extractors + seeder | All mocked |
| **Integration: e2e** | Full flow with fixture data incl. cold start | Mock LLM calls, real DB | Ollama + DeepSeek mocked |
| **Regression** | Compare new vs old on benchmark data | Side-by-side `benchmark_extraction.py` | Can run with real LLMs |

---

## Implementation Order

1. **models.py** - Data classes (no dependencies)
2. **Schema changes** - alias_key columns + KnowledgeExtractionLog + migration
3. **vertical_seeder.py** + prompt + tests - Cold start seeding
4. **item_parser.py** + tests - Reuses existing list_processor
5. **rule_extractor.py** + tests - Needs knowledge DB models + alias_key
6. **qwen_extractor.py** + prompt + tests - Needs OllamaService
7. **deepseek_consultant.py** + prompts + tests - Needs DeepSeekService
8. **pipeline.py** + tests - Orchestrates everything incl. seeder
9. **Wire into orchestrator.py** - Replace extract_entities() body
10. **E2E test** - Full integration test with suv_example_mini (incl. cold start)
11. **Manual validation** - Run on suv_example.json with real LLMs

---

## Rollout / Feature Flag

Add `ENABLE_NEW_EXTRACTION` env var (default `false`). In `orchestrator.py`:

```python
if os.getenv("ENABLE_NEW_EXTRACTION", "false").lower() == "true":
    # New pipeline
    pipeline = ExtractionPipeline(vertical, vertical_description, vertical_id, db)
    return _run_async(pipeline.extract_from_response(text))
else:
    # Existing pipeline (unchanged)
    ...
```

This allows A/B comparison and safe rollout.

---

## Evaluation: Gold Set & F0.5 Scoring

### Goal

Measure extraction quality with **F0.5** (beta=0.5), which weights precision
twice as much as recall. Target: **F0.5 ≥ 0.95**.

### Gold Set Creation

Use the full `suv_example.json` (20 prompts × ~10 items each ≈ 200 items) as
the evaluation corpus. Label manually in a Google Sheet.

**Step 1: Generate responses**

Run the 20 prompts through Qwen to get actual Chinese LLM responses. Save as
`examples/suv_gold_responses.json`:

```json
[
  {
    "prompt_index": 0,
    "prompt_text": "预算15-20万...",
    "response_text": "以下是推荐的SUV...\n1. 比亚迪宋PLUS ...\n2. ..."
  }
]
```

**Step 2: Label in Google Sheet**

Create a sheet with columns:

| prompt_index | item_position | item_text | gold_brand | gold_product | gold_brand_canonical | notes |
|---|---|---|---|---|---|---|
| 0 | 1 | 比亚迪宋PLUS DM-i - 省油... | 比亚迪 | 宋PLUS DM-i | BYD | |
| 0 | 2 | 哈弗H6 - 销量冠军... | 哈弗 | H6 | Haval | brand=长城子品牌 |
| 0 | 3 | ... | null | null | null | intro text, no entity |

Rules for labeling:
- `gold_brand`: Brand as it appears in the text (Chinese)
- `gold_product`: Product as it appears in the text (Chinese)
- `gold_brand_canonical`: English canonical name (for normalization scoring)
- `null` if item has no brand/product (e.g., intro text, generic advice)
- One brand + one product per item (same as pipeline contract)
- ~200 items total, 1-2 hours of manual labeling

**Step 3: Export to JSON**

Download as `examples/suv_gold_labels.json` for automated scoring:

```json
[
  {"prompt_index": 0, "item_position": 1, "item_text": "比亚迪宋PLUS...",
   "gold_brand": "比亚迪", "gold_product": "宋PLUS DM-i", "gold_brand_canonical": "BYD"},
  ...
]
```

### Scoring Script

`scripts/score_extraction.py` — simple, no over-engineering:

```python
"""Score extraction pipeline output against gold labels.

Usage: python scripts/score_extraction.py examples/suv_gold_labels.json [--pipeline new|old]
"""

def score_f_beta(tp: int, fp: int, fn: int, beta: float = 0.5) -> float:
    """F-beta score. beta=0.5 weights precision 2x over recall."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    beta_sq = beta ** 2
    return (1 + beta_sq) * (precision * recall) / (beta_sq * precision + recall)

def evaluate(gold_labels: list[dict], pipeline_results: list[dict]) -> dict:
    """Compare pipeline output against gold labels.

    Matching logic:
    - Brand match: exact string match OR alias match (gold_brand in pipeline brand aliases)
    - Product match: exact string match OR normalized match (strip whitespace, case)
    - An item is a TRUE POSITIVE if both brand AND product match gold
    - An item is a FALSE POSITIVE if pipeline extracted brand/product but gold is null
    - An item is a FALSE NEGATIVE if gold has brand/product but pipeline returned null

    Returns dict with:
    - brand_precision, brand_recall, brand_f05
    - product_precision, product_recall, product_f05
    - combined_precision, combined_recall, combined_f05
    - per_item_details (for debugging mismatches)
    """

def print_report(scores: dict) -> None:
    """Print human-readable scoring report."""
    # Brand extraction:  P=0.97  R=0.93  F0.5=0.96
    # Product extraction: P=0.95  R=0.91  F0.5=0.94
    # Combined:          P=0.96  R=0.92  F0.5=0.95
    # ---
    # Mismatches (top 10):
    #   Item "哈弗H6 - ..." -> predicted (长城, H6) vs gold (哈弗, H6)
```

### What to Measure

Score **three dimensions separately**:

| Metric | What counts as correct | Why |
|--------|----------------------|-----|
| **Brand extraction** | Pipeline brand matches gold brand (or alias) | Core accuracy |
| **Product extraction** | Pipeline product matches gold product | Core accuracy |
| **Brand-product pairing** | Pipeline maps product to correct brand | Relationship accuracy |

### When to Run

- **After each phase**: Run scoring to track progress
- **Old vs new comparison**: Run both pipelines on same gold set, compare F0.5
- **Regression gate**: F0.5 must not drop below 0.90 during development

### Gaps and Edge Cases to Watch

1. **Section headers parsed as items**: "5座SUV：" is not an entity — parser
   must skip these or the scorer flags them as FP
2. **Sub-brand vs brand**: 哈弗 is a sub-brand of 长城 — gold set should use
   the name as it appears (哈弗), normalization is a separate concern
3. **Items without products**: "比亚迪在新能源领域领先" mentions a brand but no
   specific product — gold label should have brand=比亚迪, product=null
4. **Multiple brands in one item**: "大众途观L和丰田RAV4对比" — current pipeline
   contract is one brand per item, so gold set should pick the primary (first)
   or we flag these as "ambiguous" and exclude from scoring
