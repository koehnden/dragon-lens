import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical
from models.domain import (
    CanonicalBrand,
    CanonicalProduct,
    EntityType,
    RunStatus,
    Sentiment,
    ValidationCandidate,
    ValidationStatus,
)


class TestConsolidateRunEndpoint:

    def test_consolidate_run_success(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Cars API Test")
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
            text_zh="测试",
            language_original="zh",
        )
        db_session.add(prompt)
        db_session.flush()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="Toyota is great",
        )
        db_session.add(answer)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Toyota",
            original_name="Toyota",
            aliases={"zh": [], "en": []},
            is_user_input=True,
        )
        db_session.add(brand)
        db_session.flush()

        mention = BrandMention(
            llm_answer_id=answer.id,
            brand_id=brand.id,
            mentioned=True,
            rank=1,
            sentiment=Sentiment.POSITIVE,
        )
        db_session.add(mention)
        db_session.commit()

        response = client.post(f"/api/v1/consolidation/runs/{run.id}/consolidate")

        assert response.status_code == 200
        data = response.json()
        assert "brands_merged" in data
        assert "products_merged" in data
        assert "brands_flagged" in data
        assert "products_flagged" in data

    def test_consolidate_run_not_found(self, client: TestClient):
        response = client.post("/api/v1/consolidation/runs/99999/consolidate")
        assert response.status_code == 404


class TestListCanonicalBrandsEndpoint:

    def test_list_canonical_brands(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Cars Brands")
        db_session.add(vertical)
        db_session.flush()

        brand1 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota",
            mention_count=10,
            is_validated=True,
        )
        brand2 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Honda",
            display_name="Honda",
            mention_count=5,
        )
        db_session.add_all([brand1, brand2])
        db_session.commit()

        response = client.get(f"/api/v1/consolidation/verticals/{vertical.id}/canonical-brands")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["canonical_name"] == "Toyota"
        assert data[0]["mention_count"] == 10
        assert data[1]["canonical_name"] == "Honda"

    def test_list_canonical_brands_empty(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Empty Vertical")
        db_session.add(vertical)
        db_session.commit()

        response = client.get(f"/api/v1/consolidation/verticals/{vertical.id}/canonical-brands")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_canonical_brands_not_found(self, client: TestClient):
        response = client.get("/api/v1/consolidation/verticals/99999/canonical-brands")
        assert response.status_code == 404


class TestListCanonicalProductsEndpoint:

    def test_list_canonical_products(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="SUV Products")
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
        db_session.commit()

        response = client.get(f"/api/v1/consolidation/verticals/{vertical.id}/canonical-products")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["canonical_name"] == "RAV4"
        assert data[1]["canonical_name"] == "CRV"

    def test_list_canonical_products_vertical_not_found(self, client: TestClient):
        response = client.get("/api/v1/consolidation/verticals/99999/canonical-products")
        assert response.status_code == 404


class TestListValidationCandidatesEndpoint:

    def test_list_validation_candidates(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Validation Test")
        db_session.add(vertical)
        db_session.flush()

        candidate1 = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Haval",
            mention_count=2,
            status=ValidationStatus.PENDING,
        )
        candidate2 = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.PRODUCT,
            name="Song Plus",
            mention_count=1,
            status=ValidationStatus.PENDING,
        )
        db_session.add_all([candidate1, candidate2])
        db_session.commit()

        response = client.get(f"/api/v1/consolidation/verticals/{vertical.id}/validation-candidates")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_validation_candidates_filter_by_type(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Filter Test")
        db_session.add(vertical)
        db_session.flush()

        brand_candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Brand X",
            status=ValidationStatus.PENDING,
        )
        product_candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.PRODUCT,
            name="Product Y",
            status=ValidationStatus.PENDING,
        )
        db_session.add_all([brand_candidate, product_candidate])
        db_session.commit()

        response = client.get(
            f"/api/v1/consolidation/verticals/{vertical.id}/validation-candidates",
            params={"entity_type": "brand"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Brand X"

    def test_list_validation_candidates_invalid_type(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Invalid Type Test")
        db_session.add(vertical)
        db_session.commit()

        response = client.get(
            f"/api/v1/consolidation/verticals/{vertical.id}/validation-candidates",
            params={"entity_type": "invalid"}
        )

        assert response.status_code == 400

    def test_list_validation_candidates_vertical_not_found(self, client: TestClient):
        response = client.get("/api/v1/consolidation/verticals/99999/validation-candidates")
        assert response.status_code == 404


class TestValidateCandidateEndpoint:

    def test_validate_candidate_approve(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Approve Test")
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
        db_session.commit()

        response = client.post(
            f"/api/v1/consolidation/validation-candidates/{candidate.id}/validate",
            json={"approved": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validated"
        assert data["reviewed_by"] == "user"

    def test_validate_candidate_reject(self, client: TestClient, db_session: Session):
        vertical = Vertical(name="Reject Test")
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
        db_session.commit()

        response = client.post(
            f"/api/v1/consolidation/validation-candidates/{candidate.id}/validate",
            json={"approved": False, "rejection_reason": "Generic term"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Generic term"

    def test_validate_candidate_not_found(self, client: TestClient):
        response = client.post(
            "/api/v1/consolidation/validation-candidates/99999/validate",
            json={"approved": True}
        )
        assert response.status_code == 404


class TestCanonicalBrandWithAliases:

    def test_canonical_brand_includes_aliases(self, client: TestClient, db_session: Session):
        from models.domain import BrandAlias

        vertical = Vertical(name="Alias Test")
        db_session.add(vertical)
        db_session.flush()

        brand = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Volkswagen",
            display_name="Volkswagen",
            mention_count=10,
        )
        db_session.add(brand)
        db_session.flush()

        alias1 = BrandAlias(canonical_brand_id=brand.id, alias="VW")
        alias2 = BrandAlias(canonical_brand_id=brand.id, alias="大众")
        db_session.add_all([alias1, alias2])
        db_session.commit()

        response = client.get(f"/api/v1/consolidation/verticals/{vertical.id}/canonical-brands")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["canonical_name"] == "Volkswagen"
        assert len(data[0]["aliases"]) == 2
        assert "VW" in data[0]["aliases"]
        assert "大众" in data[0]["aliases"]
