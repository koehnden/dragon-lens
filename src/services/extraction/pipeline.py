"""Run-level extraction pipeline."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session

from models.domain import EntityType
from models.knowledge_database import KnowledgeWriteSessionLocal
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeExtractionLog,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
)
from services.brand_recognition.models import ExtractionDebugInfo, ExtractionResult
from services.extraction.deepseek_consultant import DeepSeekConsultant
from services.extraction.item_parser import extract_intro_context, parse_response_into_items
from services.extraction.latin_extractor import extract_latin_tokens
from services.extraction.models import BatchExtractionResult, BrandProductPair, ItemExtractionResult, PipelineDebugInfo
from services.extraction.qwen_extractor import QwenBatchExtractor
from services.extraction.rule_extractor import KnowledgeBaseMatcher
from services.extraction.vertical_seeder import VerticalSeeder
from services.knowledge_verticals import get_or_create_vertical, normalize_entity_key


class ExtractionPipeline:
    """Run-scoped extraction pipeline shared across a full prompt set."""

    def __init__(
        self,
        vertical: str,
        vertical_description: str,
        *,
        db: Session | None = None,
        run_id: int | None = None,
        knowledge_db: Session | None = None,
    ):
        self.vertical = vertical
        self.vertical_description = vertical_description
        self.db = db
        self.run_id = run_id
        self._owns_knowledge_db = knowledge_db is None
        self.knowledge_db = knowledge_db or KnowledgeWriteSessionLocal()
        self.knowledge_vertical = get_or_create_vertical(self.knowledge_db, vertical)
        if vertical_description and not self.knowledge_vertical.description:
            self.knowledge_vertical.description = vertical_description
        self.knowledge_vertical_id = self.knowledge_vertical.id

        self._seed_checked = False
        self._matcher: KnowledgeBaseMatcher | None = None
        self._response_results: dict[str, list[ItemExtractionResult]] = {}
        self.debug_info = PipelineDebugInfo()

    def close(self) -> None:
        if self._owns_knowledge_db:
            self.knowledge_db.close()

    def _get_matcher(self) -> KnowledgeBaseMatcher:
        if self._matcher is None:
            self._matcher = KnowledgeBaseMatcher(self.knowledge_vertical_id, self.knowledge_db)
        return self._matcher

    async def process_response(
        self,
        text: str,
        *,
        response_id: str | None = None,
        user_brands: list | None = None,
    ) -> ExtractionResult:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[PIPELINE] process_response starting, response_id={response_id}")

        if not self._seed_checked:
            logger.info(f"[PIPELINE] Ensuring seeded...")
            await self._ensure_seeded(user_brands or [])
            self._seed_checked = True
            self._matcher = KnowledgeBaseMatcher(self.knowledge_vertical_id, self.knowledge_db)
            logger.info(f"[PIPELINE] Seeding completed")

        logger.info(f"[PIPELINE] Parsing items...")
        items = parse_response_into_items(text, response_id=response_id)
        intro_context = extract_intro_context(text)
        self.debug_info.step0_item_count += len(items)
        self.debug_info.step0_response_count += 1
        logger.info(f"[PIPELINE] Parsed {len(items)} items")

        logger.info(f"[PIPELINE] Matching items against KB...")
        matcher = self._get_matcher()
        item_results = [matcher.match_item(item) for item in items]
        logger.info(f"[PIPELINE] KB matching completed")

        missing_items = []
        for result in item_results:
            if _needs_qwen(result):
                missing_items.append((result.item, result.brand, result.product))
            else:
                self._record_kb_hits(result)
        logger.info(f"[PIPELINE] Found {len(missing_items)} items needing Qwen extraction")

        if missing_items:
            logger.info(f"[PIPELINE] Creating QwenBatchExtractor...")
            qwen = QwenBatchExtractor(
                self.vertical,
                self.vertical_description,
                vertical_id=self.knowledge_vertical_id,
                knowledge_db=self.knowledge_db,
            )
            logger.info(f"[PIPELINE] Calling qwen.extract_missing...")
            qwen_results = await qwen.extract_missing(
                missing_items,
                {response_id: intro_context} if intro_context else {},
            )
            logger.info(f"[PIPELINE] Qwen extraction completed, got {len(qwen_results)} results")
            self.debug_info.step2_qwen_input_count += len(missing_items)
            self.debug_info.step2_qwen_batch_count += 1
            item_results = _merge_item_results(item_results, qwen_results)
            for result in qwen_results:
                for pair in result.pairs:
                    matcher.add_to_session(pair.brand, pair.product)
                    if pair.brand:
                        self.debug_info.step2_qwen_extracted_brands.append(pair.brand)
                    if pair.product:
                        self.debug_info.step2_qwen_extracted_products.append(pair.product)

        item_results = _enrich_with_latin_tokens(item_results)

        if response_id is None:
            response_id = f"response-{len(self._response_results)}"
        self._response_results[response_id] = item_results
        logger.info(f"[PIPELINE] Building response result...")
        result = self._build_response_result(item_results)
        logger.info(f"[PIPELINE] process_response completed successfully")
        return result

    async def finalize(self) -> BatchExtractionResult:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[EXTRACTION] finalize() starting for vertical={self.vertical}")

        consultant = DeepSeekConsultant(
            self.vertical,
            self.vertical_description,
            vertical_id=self.knowledge_vertical_id,
            knowledge_db=self.knowledge_db,
        )
        logger.info(f"[EXTRACTION] DeepSeekConsultant created")

        all_results = [item for results in self._response_results.values() for item in results]
        raw_pairs = [pair for item in all_results for pair in item.pairs]
        raw_brands = _ordered_unique(pair.brand for pair in raw_pairs if pair.brand)
        raw_products = _ordered_unique(pair.product for pair in raw_pairs if pair.product)
        logger.info(f"[EXTRACTION] Collected {len(raw_brands)} brands, {len(raw_products)} products")

        logger.info(f"[EXTRACTION] Calling normalize_and_map...")
        brand_aliases, product_aliases, product_brand_map = await consultant.normalize_and_map(
            raw_brands,
            raw_products,
            [(pair.brand, pair.product) for pair in raw_pairs],
        )
        logger.info(f"[EXTRACTION] normalize_and_map completed: {len(brand_aliases)} brand aliases, {len(product_aliases)} product aliases")

        logger.info(f"[EXTRACTION] Calling validate_relevance...")
        valid_brands, valid_products, rejected_brands, rejected_products, rejection_reasons = (
            await consultant.validate_relevance(
                list({brand_aliases.get(brand, brand) for brand in raw_brands}),
                list({product_aliases.get(product, product) for product in raw_products}),
            )
        )
        logger.info(f"[EXTRACTION] validate_relevance completed: {len(valid_brands)} valid brands, {len(valid_products)} valid products")

        logger.info(f"[EXTRACTION] Storing rejections...")
        consultant.store_rejections(rejected_brands, rejected_products, rejection_reasons)
        logger.info(f"[EXTRACTION] store_rejections completed")

        logger.info(f"[EXTRACTION] Creating BatchExtractionResult...")
        batch = BatchExtractionResult(
            items=all_results,
            brand_aliases=brand_aliases,
            product_aliases=product_aliases,
            product_brand_map=product_brand_map,
            validated_brands=valid_brands,
            validated_products=valid_products,
            rejected_brands=rejected_brands,
            rejected_products=rejected_products,
        )
        logger.info(f"[EXTRACTION] BatchExtractionResult created")

        logger.info(f"[EXTRACTION] Persisting knowledge to database...")
        self._persist_knowledge(batch)
        logger.info(f"[EXTRACTION] Knowledge persistence completed")

        logger.info(f"[EXTRACTION] Finalizing {len(self._response_results)} response results...")
        for response_id, item_results in self._response_results.items():
            finalized_items = _finalize_item_results(
                item_results,
                brand_aliases=brand_aliases,
                product_aliases=product_aliases,
                product_brand_map=product_brand_map,
                valid_brands=valid_brands,
                valid_products=valid_products,
            )
            extraction_result = self._build_response_result(finalized_items)
            batch.response_results[response_id] = extraction_result
        logger.info(f"[EXTRACTION] Response results finalized")

        self.debug_info.step3_normalized_brands = dict(brand_aliases)
        self.debug_info.step3_normalized_products = dict(product_aliases)
        self.debug_info.step3_product_brand_map = dict(product_brand_map)
        self.debug_info.step3_rejected_brands = sorted(rejected_brands)
        self.debug_info.step3_rejected_products = sorted(rejected_products)

        logger.info(f"[EXTRACTION] Flushing and committing knowledge DB...")
        self.knowledge_db.flush()
        if self._owns_knowledge_db:
            self.knowledge_db.commit()
        logger.info(f"[EXTRACTION] finalize() completed successfully")
        return batch

    async def _ensure_seeded(self, user_brands: list) -> None:
        seeder = VerticalSeeder(self.vertical, self.vertical_description, self.knowledge_vertical_id)
        user_brand_dicts = [_brand_to_seed_dict(brand) for brand in user_brands]
        before = self.knowledge_vertical.seeded_at
        await seeder.ensure_seeded(self.knowledge_db, user_brand_dicts)
        self.debug_info.knowledge_seeded = before is None and self.knowledge_vertical.seeded_at is not None

    def _record_kb_hits(self, result: ItemExtractionResult) -> None:
        for pair in result.pairs:
            if pair.brand and pair.brand_source == "kb":
                self.debug_info.step1_kb_matched_brands.append(pair.brand)
            if pair.product and pair.product_source == "kb":
                self.debug_info.step1_kb_matched_products.append(pair.product)

    def _build_response_result(self, item_results: list[ItemExtractionResult]) -> ExtractionResult:
        brands: dict[str, list[str]] = defaultdict(list)
        products: dict[str, list[str]] = defaultdict(list)
        relationships: dict[str, str] = {}
        raw_brands: list[str] = []
        raw_products: list[str] = []

        for result in item_results:
            for pair in result.pairs:
                if pair.brand:
                    raw_brands.append(pair.brand)
                    if pair.brand not in brands[pair.brand]:
                        brands[pair.brand].append(pair.brand)
                if pair.product:
                    raw_products.append(pair.product)
                    if pair.product not in products[pair.product]:
                        products[pair.product].append(pair.product)
                if pair.brand and pair.product:
                    relationships[pair.product] = pair.brand

        debug_info = ExtractionDebugInfo(
            raw_brands=raw_brands,
            raw_products=raw_products,
            rejected_at_light_filter=[],
            final_brands=list(brands.keys()),
            final_products=list(products.keys()),
        )
        return ExtractionResult(
            brands=dict(brands),
            products=dict(products),
            product_brand_relationships=relationships,
            debug_info=debug_info,
        )

    def _persist_knowledge(self, batch: BatchExtractionResult) -> None:
        brand_rows: dict[str, KnowledgeBrand] = {}

        for canonical in sorted(batch.validated_brands):
            brand_rows[canonical] = _upsert_brand(self.knowledge_db, self.knowledge_vertical_id, canonical)

        for alias, canonical in batch.brand_aliases.items():
            if canonical not in batch.validated_brands:
                continue
            brand = brand_rows.setdefault(
                canonical,
                _upsert_brand(self.knowledge_db, self.knowledge_vertical_id, canonical),
            )
            _upsert_brand_alias(self.knowledge_db, brand.id, alias)

        product_rows: dict[str, KnowledgeProduct] = {}
        for canonical in sorted(batch.validated_products):
            mapped_brand_name = batch.product_brand_map.get(canonical)
            mapped_brand = brand_rows.get(mapped_brand_name) if mapped_brand_name else None
            product_rows[canonical] = _upsert_product(
                self.knowledge_db,
                self.knowledge_vertical_id,
                canonical,
                brand_id=mapped_brand.id if mapped_brand else None,
            )

        for alias, canonical in batch.product_aliases.items():
            if canonical not in batch.validated_products:
                continue
            product = product_rows.setdefault(
                canonical,
                _upsert_product(self.knowledge_db, self.knowledge_vertical_id, canonical),
            )
            _upsert_product_alias(self.knowledge_db, product.id, alias)

        for product_name, brand_name in batch.product_brand_map.items():
            if product_name not in batch.validated_products or brand_name not in batch.validated_brands:
                continue
            product = product_rows.setdefault(
                product_name,
                _upsert_product(self.knowledge_db, self.knowledge_vertical_id, product_name),
            )
            brand = brand_rows.setdefault(
                brand_name,
                _upsert_brand(self.knowledge_db, self.knowledge_vertical_id, brand_name),
            )
            if not product.brand_id:
                product.brand_id = brand.id
            _upsert_product_brand_mapping(
                self.knowledge_db,
                self.knowledge_vertical_id,
                product.id,
                brand.id,
            )

        self._write_extraction_logs(batch)

    def _write_extraction_logs(self, batch: BatchExtractionResult) -> None:
        for item in batch.items:
            for pair in item.pairs:
                if pair.brand:
                    canonical_brand = batch.brand_aliases.get(pair.brand, pair.brand)
                    self.knowledge_db.add(
                        KnowledgeExtractionLog(
                            vertical_id=self.knowledge_vertical_id,
                            run_id=self.run_id,
                            entity_name=pair.brand,
                            entity_type=EntityType.BRAND,
                            extraction_source=pair.brand_source or "pipeline",
                            resolved_to=canonical_brand,
                            was_accepted=canonical_brand in batch.validated_brands,
                            item_text=item.item.text,
                        )
                    )
                if pair.product:
                    canonical_product = batch.product_aliases.get(pair.product, pair.product)
                    self.knowledge_db.add(
                        KnowledgeExtractionLog(
                            vertical_id=self.knowledge_vertical_id,
                            run_id=self.run_id,
                            entity_name=pair.product,
                            entity_type=EntityType.PRODUCT,
                            extraction_source=pair.product_source or "pipeline",
                            resolved_to=canonical_product,
                            was_accepted=canonical_product in batch.validated_products,
                            item_text=item.item.text,
                        )
                    )


def _brand_to_seed_dict(brand: object) -> dict:
    if isinstance(brand, dict):
        aliases = brand.get("aliases", None) or {"zh": [], "en": []}
        return {
            "display_name": brand.get("display_name", ""),
            "aliases": {
                "zh": list(aliases.get("zh", [])),
                "en": list(aliases.get("en", [])),
            },
        }
    aliases = getattr(brand, "aliases", None) or {"zh": [], "en": []}
    return {
        "display_name": getattr(brand, "display_name", ""),
        "aliases": {
            "zh": list(aliases.get("zh", [])),
            "en": list(aliases.get("en", [])),
        },
    }


def _needs_qwen(result: ItemExtractionResult) -> bool:
    if not result.pairs:
        return True
    return any(not pair.brand or not pair.product for pair in result.pairs)


def _merge_item_results(
    base_results: list[ItemExtractionResult],
    qwen_results: list[ItemExtractionResult],
) -> list[ItemExtractionResult]:
    qwen_by_position = {result.item.position: result for result in qwen_results}
    merged: list[ItemExtractionResult] = []
    for result in base_results:
        qwen_result = qwen_by_position.get(result.item.position)
        if not qwen_result:
            merged.append(result)
            continue
        pairs = list(result.pairs)
        seen = {(pair.brand, pair.product) for pair in pairs}
        for pair in qwen_result.pairs:
            if (pair.brand, pair.product) in seen:
                continue
            pairs.append(pair)
            seen.add((pair.brand, pair.product))
        merged.append(ItemExtractionResult(item=result.item, pairs=pairs))
    return merged



def _finalize_item_results(
    item_results: list[ItemExtractionResult],
    *,
    brand_aliases: dict[str, str],
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
    valid_brands: set[str],
    valid_products: set[str],
) -> list[ItemExtractionResult]:
    finalized: list[ItemExtractionResult] = []
    for result in item_results:
        pairs: list[BrandProductPair] = []
        for pair in result.pairs:
            canonical_brand = brand_aliases.get(pair.brand, pair.brand) if pair.brand else None
            canonical_product = product_aliases.get(pair.product, pair.product) if pair.product else None
            if canonical_product and canonical_product in product_brand_map:
                canonical_brand = product_brand_map[canonical_product]

            if canonical_brand and canonical_brand not in valid_brands:
                canonical_brand = None
            if canonical_product and canonical_product not in valid_products:
                canonical_product = None
            if not canonical_brand and not canonical_product:
                continue

            pairs.append(
                BrandProductPair(
                    brand=canonical_brand,
                    product=canonical_product,
                    brand_source=pair.brand_source,
                    product_source=pair.product_source,
                )
            )
        finalized.append(ItemExtractionResult(item=result.item, pairs=pairs))
    return finalized


def _upsert_brand(db: Session, vertical_id: int, canonical_name: str) -> KnowledgeBrand:
    alias_key = normalize_entity_key(canonical_name)
    brand = (
        db.query(KnowledgeBrand)
        .filter(
            KnowledgeBrand.vertical_id == vertical_id,
            KnowledgeBrand.alias_key == alias_key,
        )
        .first()
    )
    if brand:
        brand.is_validated = True
        brand.validation_source = _preferred_validation_source(brand.validation_source)
        return brand
    brand = KnowledgeBrand(
        vertical_id=vertical_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        is_validated=True,
        validation_source="pipeline",
    )
    db.add(brand)
    db.flush()
    return brand


def _upsert_brand_alias(db: Session, brand_id: int, alias: str) -> None:
    alias_key = normalize_entity_key(alias)
    existing = (
        db.query(KnowledgeBrandAlias)
        .filter(
            KnowledgeBrandAlias.brand_id == brand_id,
            KnowledgeBrandAlias.alias_key == alias_key,
        )
        .first()
    )
    if existing:
        return
    db.add(KnowledgeBrandAlias(brand_id=brand_id, alias=alias))


def _upsert_product(
    db: Session,
    vertical_id: int,
    canonical_name: str,
    *,
    brand_id: int | None = None,
) -> KnowledgeProduct:
    alias_key = normalize_entity_key(canonical_name)
    product = (
        db.query(KnowledgeProduct)
        .filter(
            KnowledgeProduct.vertical_id == vertical_id,
            KnowledgeProduct.alias_key == alias_key,
        )
        .first()
    )
    if product:
        product.is_validated = True
        product.validation_source = _preferred_validation_source(product.validation_source)
        if brand_id and not product.brand_id:
            product.brand_id = brand_id
        return product
    product = KnowledgeProduct(
        vertical_id=vertical_id,
        brand_id=brand_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        is_validated=True,
        validation_source="pipeline",
    )
    db.add(product)
    db.flush()
    return product


def _upsert_product_alias(db: Session, product_id: int, alias: str) -> None:
    alias_key = normalize_entity_key(alias)
    existing = (
        db.query(KnowledgeProductAlias)
        .filter(
            KnowledgeProductAlias.product_id == product_id,
            KnowledgeProductAlias.alias_key == alias_key,
        )
        .first()
    )
    if existing:
        return
    db.add(KnowledgeProductAlias(product_id=product_id, alias=alias))


def _upsert_product_brand_mapping(
    db: Session,
    vertical_id: int,
    product_id: int,
    brand_id: int,
) -> None:
    existing = (
        db.query(KnowledgeProductBrandMapping)
        .filter(
            KnowledgeProductBrandMapping.vertical_id == vertical_id,
            KnowledgeProductBrandMapping.product_id == product_id,
            KnowledgeProductBrandMapping.brand_id == brand_id,
        )
        .first()
    )
    if existing:
        existing.is_validated = True
        existing.source = "pipeline"
        return
    db.add(
        KnowledgeProductBrandMapping(
            vertical_id=vertical_id,
            product_id=product_id,
            brand_id=brand_id,
            is_validated=True,
            source="pipeline",
        )
    )


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _enrich_with_latin_tokens(
    item_results: list[ItemExtractionResult],
) -> list[ItemExtractionResult]:
    for result in item_results:
        latin_tokens = extract_latin_tokens(result.item.text)
        existing = {
            name.lower()
            for pair in result.pairs
            for name in (pair.brand, pair.product)
            if name
        }
        for token in latin_tokens:
            if token.lower() in existing:
                continue
            if _is_substring_of_existing(token, existing):
                continue
            result.pairs.append(
                BrandProductPair(brand=token, product=None, brand_source="latin", product_source="")
            )
    return item_results


def _is_substring_of_existing(token: str, existing: set[str]) -> bool:
    token_lower = token.lower()
    return any(token_lower in name for name in existing)


def _preferred_validation_source(existing_source: str | None) -> str:
    if existing_source == "user":
        return "user"
    return "pipeline"
