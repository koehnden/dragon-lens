import pytest
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Product, ProductMention, Prompt, Run, Vertical
from models.domain import (
    BrandAlias,
    CanonicalBrand,
    CanonicalProduct,
    EntityType,
    RejectedEntity,
    RunStatus,
    Sentiment,
    ValidationCandidate,
    ValidationStatus,
)
from services.entity_consolidation import (
    ConsolidationResult,
    MergeCandidate,
    _calculate_similarity,
    _build_qwen_brand_candidates,
    _determine_canonical,
    _normalize_for_comparison,
    apply_brand_merges,
    apply_product_merges,
    consolidate_run,
    find_merge_candidates,
    flag_low_frequency_brands,
    flag_low_frequency_products,
    get_canonical_brands,
    get_canonical_products,
    get_pending_candidates,
    validate_candidate,
)


class TestNormalizeForComparison:

    def test_lowercase_and_strip(self):
        assert _normalize_for_comparison("  Toyota  ") == "toyota"

    def test_removes_spaces_and_hyphens(self):
        assert _normalize_for_comparison("The North Face") == "thenorthface"
        assert _normalize_for_comparison("Mercedes-Benz") == "mercedesbenz"

    def test_removes_brackets(self):
        assert _normalize_for_comparison("Toyota (丰田)") == "toyota"

    def test_removes_punctuation(self):
        assert _normalize_for_comparison("Goo.n") == "goon"

    def test_chinese_characters_preserved(self):
        assert _normalize_for_comparison("比亚迪") == "比亚迪"


class TestCalculateSimilarity:

    def test_identical_strings(self):
        assert _calculate_similarity("toyota", "toyota") == 1.0

    def test_substring_match(self):
        sim = _calculate_similarity("bmw", "bmwx5")
        assert sim > 0.5

    def test_different_strings(self):
        sim = _calculate_similarity("toyota", "honda")
        assert sim < 0.5

    def test_similar_strings(self):
        sim = _calculate_similarity("volkswagen", "volkswagon")
        assert sim > 0.8


class TestDetermineCanonical:

    def test_prefers_shorter_clean_name(self):
        target, source = _determine_canonical("Ford Motor Company", "Ford")
        assert target == "Ford"
        assert source == "Ford Motor Company"

    def test_same_length_alphabetical(self):
        target, source = _determine_canonical("BMW", "VWA")
        assert target == "BMW"
        assert source == "VWA"


class TestFindMergeCandidates:

    def test_finds_similar_brands(self):
        names = ["Volkswagen", "Volkswagon", "Toyota", "BMW"]
        candidates = find_merge_candidates(names, EntityType.BRAND)

        vw_merge = next(
            (c for c in candidates if "Volkswagen" in [c.source_name, c.target_name]),
            None
        )
        assert vw_merge is not None
        assert vw_merge.similarity > 0.85

    def test_no_false_positives(self):
        names = ["Toyota", "Honda", "BMW", "Mercedes"]
        candidates = find_merge_candidates(names, EntityType.BRAND)
        assert len(candidates) == 0

    def test_near_identical_merge(self):
        names = ["Model Y", "ModelY", "RAV4"]
        candidates = find_merge_candidates(names, EntityType.BRAND)

        model_merge = next(
            (c for c in candidates if "Model" in c.target_name),
            None
        )
        assert model_merge is not None
        assert model_merge.similarity > 0.85

    def test_empty_list(self):
        candidates = find_merge_candidates([], EntityType.BRAND)
        assert candidates == []

    def test_single_item(self):
        candidates = find_merge_candidates(["Toyota"], EntityType.BRAND)
        assert candidates == []


class TestApplyBrandMerges:

    def test_merges_brands_into_canonical(self, db_session: Session):
        vertical = Vertical(name="Cars")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"Volkswagen": 5, "VW": 3}
        candidates = [
            MergeCandidate(
                source_name="VW",
                target_name="Volkswagen",
                similarity=0.9,
                entity_type=EntityType.BRAND,
            )
        ]

        merged = apply_brand_merges(db_session, vertical.id, mentions, candidates)

        assert merged == 1

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.canonical_name == "Volkswagen"
        ).first()
        assert canonical is not None
        assert canonical.mention_count == 8

        aliases = db_session.query(BrandAlias).filter(
            BrandAlias.canonical_brand_id == canonical.id
        ).all()
        assert len(aliases) == 1
        assert aliases[0].alias == "VW"

    def test_creates_canonical_for_unmerged(self, db_session: Session):
        vertical = Vertical(name="Cars2")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"Toyota": 10, "Honda": 5}
        candidates = []

        apply_brand_merges(db_session, vertical.id, mentions, candidates)

        canonicals = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.vertical_id == vertical.id
        ).all()
        assert len(canonicals) == 2
        names = [c.canonical_name for c in canonicals]
        assert "Toyota" in names
        assert "Honda" in names


class TestQwenCanonicalGroups:

    def test_user_brand_overrides_qwen(self, db_session: Session):
        vertical = Vertical(name="CarsQ1")
        db_session.add(vertical)
        db_session.flush()

        user_brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"zh": [], "en": []},
            is_user_input=True,
        )
        discovered_brand = Brand(
            vertical_id=vertical.id,
            display_name="Volkswagen",
            original_name="Volkswagen",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        db_session.add_all([user_brand, discovered_brand])
        db_session.flush()

        mentions = {"VW": 2, "Volkswagen": 1}
        normalized_brands = {"VW": "Volkswagen", "Volkswagen": "Volkswagen"}

        candidates, _ = _build_qwen_brand_candidates(
            db_session, vertical.id, normalized_brands
        )

        apply_brand_merges(
            db_session,
            vertical.id,
            mentions,
            candidates,
        )

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.canonical_name == "VW"
        ).first()
        assert canonical is not None
        assert canonical.mention_count == 3

        aliases = db_session.query(BrandAlias).filter(
            BrandAlias.canonical_brand_id == canonical.id
        ).all()
        assert len(aliases) == 1
        assert aliases[0].alias == "Volkswagen"

    def test_qwen_canonical_used_when_in_group(self, db_session: Session):
        vertical = Vertical(name="CarsQ2")
        db_session.add(vertical)
        db_session.flush()

        brand1 = Brand(
            vertical_id=vertical.id,
            display_name="Unicharm",
            original_name="Unicharm",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        brand2 = Brand(
            vertical_id=vertical.id,
            display_name="Unicharm (尤妮佳)",
            original_name="Unicharm (尤妮佳)",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        mentions = {"Unicharm": 1, "Unicharm (尤妮佳)": 2}
        normalized_brands = {
            "Unicharm": "Unicharm",
            "Unicharm (尤妮佳)": "Unicharm",
        }

        candidates, _ = _build_qwen_brand_candidates(
            db_session, vertical.id, normalized_brands
        )

        apply_brand_merges(
            db_session,
            vertical.id,
            mentions,
            candidates,
        )

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.canonical_name == "Unicharm"
        ).first()
        assert canonical is not None
        assert canonical.mention_count == 3

        aliases = db_session.query(BrandAlias).filter(
            BrandAlias.canonical_brand_id == canonical.id
        ).all()
        assert len(aliases) == 1
        assert aliases[0].alias == "Unicharm (尤妮佳)"

    def test_fallback_when_qwen_canonical_not_in_group(self, db_session: Session):
        vertical = Vertical(name="CarsQ3")
        db_session.add(vertical)
        db_session.flush()

        brand1 = Brand(
            vertical_id=vertical.id,
            display_name="Ford Motor Company of Canada",
            original_name="Ford Motor Company of Canada",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        brand2 = Brand(
            vertical_id=vertical.id,
            display_name="Ford Motor Canada",
            original_name="Ford Motor Canada",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        mentions = {
            "Ford Motor Company of Canada": 2,
            "Ford Motor Canada": 1,
        }
        normalized_brands = {
            "Ford Motor Company of Canada": "Ford",
            "Ford Motor Canada": "Ford",
        }

        candidates, _ = _build_qwen_brand_candidates(
            db_session, vertical.id, normalized_brands
        )

        apply_brand_merges(
            db_session,
            vertical.id,
            mentions,
            candidates,
        )

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.canonical_name == "Ford Motor Canada"
        ).first()
        assert canonical is not None
        assert canonical.mention_count == 3


class TestApplyProductMerges:

    def test_merges_products(self, db_session: Session):
        vertical = Vertical(name="SUV")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"Model Y": 5, "ModelY": 2}
        candidates = [
            MergeCandidate(
                source_name="ModelY",
                target_name="Model Y",
                similarity=0.95,
                entity_type=EntityType.PRODUCT,
            )
        ]

        merged = apply_product_merges(db_session, vertical.id, mentions, candidates)

        assert merged == 1

        canonical = db_session.query(CanonicalProduct).filter(
            CanonicalProduct.canonical_name == "Model Y"
        ).first()
        assert canonical is not None
        assert canonical.mention_count == 7


class TestFlagLowFrequencyBrands:

    def test_flags_low_frequency_brands(self, db_session: Session):
        vertical = Vertical(name="Cars3")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"Toyota": 10, "Haval": 1, "Geely": 2}

        flagged = flag_low_frequency_brands(db_session, vertical.id, mentions)

        assert flagged == 2

        candidates = db_session.query(ValidationCandidate).filter(
            ValidationCandidate.vertical_id == vertical.id,
            ValidationCandidate.entity_type == EntityType.BRAND,
        ).all()
        assert len(candidates) == 2
        names = [c.name for c in candidates]
        assert "Haval" in names
        assert "Geely" in names

    def test_skips_high_frequency_brands(self, db_session: Session):
        vertical = Vertical(name="Cars4")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"Toyota": 10, "Honda": 5}

        flagged = flag_low_frequency_brands(db_session, vertical.id, mentions)

        assert flagged == 0


class TestFlagLowFrequencyProducts:

    def test_flags_low_frequency_products(self, db_session: Session):
        vertical = Vertical(name="SUV2")
        db_session.add(vertical)
        db_session.flush()

        mentions = {"RAV4": 5, "Unknown Model": 1}

        flagged = flag_low_frequency_products(db_session, vertical.id, mentions)

        assert flagged == 1

        candidate = db_session.query(ValidationCandidate).filter(
            ValidationCandidate.name == "Unknown Model"
        ).first()
        assert candidate is not None
        assert candidate.entity_type == EntityType.PRODUCT


class TestValidateCandidate:

    def test_approve_candidate(self, db_session: Session):
        vertical = Vertical(name="Cars5")
        db_session.add(vertical)
        db_session.flush()

        candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Haval",
            mention_count=2,
            status=ValidationStatus.PENDING,
        )
        db_session.add(candidate)
        db_session.flush()

        result = validate_candidate(db_session, candidate.id, approved=True)

        assert result.status == ValidationStatus.VALIDATED
        assert result.reviewed_by == "user"

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.canonical_name == "Haval"
        ).first()
        assert canonical is not None

    def test_reject_candidate(self, db_session: Session):
        vertical = Vertical(name="Cars6")
        db_session.add(vertical)
        db_session.flush()

        candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Not A Brand",
            mention_count=1,
            status=ValidationStatus.PENDING,
        )
        db_session.add(candidate)
        db_session.flush()

        result = validate_candidate(
            db_session, candidate.id,
            approved=False,
            rejection_reason="Generic term"
        )

        assert result.status == ValidationStatus.REJECTED
        assert result.rejection_reason == "Generic term"

        rejected = db_session.query(RejectedEntity).filter(
            RejectedEntity.name == "Not A Brand"
        ).first()
        assert rejected is not None

    def test_validate_nonexistent_candidate(self, db_session: Session):
        with pytest.raises(ValueError, match="not found"):
            validate_candidate(db_session, 99999, approved=True)


class TestGetPendingCandidates:

    def test_returns_pending_candidates(self, db_session: Session):
        vertical = Vertical(name="Cars7")
        db_session.add(vertical)
        db_session.flush()

        pending = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Pending Brand",
            status=ValidationStatus.PENDING,
        )
        validated = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Validated Brand",
            status=ValidationStatus.VALIDATED,
        )
        db_session.add_all([pending, validated])
        db_session.flush()

        result = get_pending_candidates(db_session, vertical.id)

        assert len(result) == 1
        assert result[0].name == "Pending Brand"

    def test_filters_by_entity_type(self, db_session: Session):
        vertical = Vertical(name="Cars8")
        db_session.add(vertical)
        db_session.flush()

        brand = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Brand",
            status=ValidationStatus.PENDING,
        )
        product = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.PRODUCT,
            name="Product",
            status=ValidationStatus.PENDING,
        )
        db_session.add_all([brand, product])
        db_session.flush()

        brands = get_pending_candidates(db_session, vertical.id, EntityType.BRAND)
        products = get_pending_candidates(db_session, vertical.id, EntityType.PRODUCT)

        assert len(brands) == 1
        assert brands[0].name == "Brand"
        assert len(products) == 1
        assert products[0].name == "Product"


class TestGetCanonicalBrands:

    def test_returns_canonical_brands_sorted(self, db_session: Session):
        vertical = Vertical(name="Cars9")
        db_session.add(vertical)
        db_session.flush()

        brand1 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota",
            mention_count=10,
        )
        brand2 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Honda",
            display_name="Honda",
            mention_count=5,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        result = get_canonical_brands(db_session, vertical.id)

        assert len(result) == 2
        assert result[0].canonical_name == "Toyota"
        assert result[1].canonical_name == "Honda"


class TestGetCanonicalProducts:

    def test_returns_canonical_products_sorted(self, db_session: Session):
        vertical = Vertical(name="SUV3")
        db_session.add(vertical)
        db_session.flush()

        prod1 = CanonicalProduct(
            vertical_id=vertical.id,
            canonical_name="RAV4",
            display_name="RAV4",
            mention_count=8,
        )
        prod2 = CanonicalProduct(
            vertical_id=vertical.id,
            canonical_name="CRV",
            display_name="CRV",
            mention_count=3,
        )
        db_session.add_all([prod1, prod2])
        db_session.flush()

        result = get_canonical_products(db_session, vertical.id)

        assert len(result) == 2
        assert result[0].canonical_name == "RAV4"
        assert result[1].canonical_name == "CRV"


class TestConsolidateRun:

    def test_consolidate_run_full_workflow(self, db_session: Session):
        vertical = Vertical(name="Full Test")
        db_session.add(vertical)
        db_session.flush()

        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.COMPLETED,
        )
        db_session.add(run)
        db_session.flush()

        prompt = Prompt(
            run_id=run.id,
            vertical_id=vertical.id,
            text_zh="测试提示",
            language_original="zh",
        )
        db_session.add(prompt)
        db_session.flush()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="丰田和本田都很好",
        )
        db_session.add(answer)
        db_session.flush()

        brand1 = Brand(
            vertical_id=vertical.id,
            display_name="Toyota",
            original_name="Toyota",
            aliases={"zh": ["丰田"], "en": []},
            is_user_input=True,
        )
        brand2 = Brand(
            vertical_id=vertical.id,
            display_name="Honda",
            original_name="Honda",
            aliases={"zh": ["本田"], "en": []},
            is_user_input=True,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        mention1 = BrandMention(
            llm_answer_id=answer.id,
            brand_id=brand1.id,
            mentioned=True,
            rank=1,
            sentiment=Sentiment.POSITIVE,
        )
        mention2 = BrandMention(
            llm_answer_id=answer.id,
            brand_id=brand2.id,
            mentioned=True,
            rank=2,
            sentiment=Sentiment.POSITIVE,
        )
        db_session.add_all([mention1, mention2])
        db_session.flush()

        result = consolidate_run(db_session, run.id)

        assert isinstance(result, ConsolidationResult)
        assert result.canonical_brands_created >= 0

    def test_consolidate_run_not_found(self, db_session: Session):
        with pytest.raises(ValueError, match="not found"):
            consolidate_run(db_session, 99999)
