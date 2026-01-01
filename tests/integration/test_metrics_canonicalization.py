import pytest

from models import (
    Brand,
    BrandAlias,
    BrandMention,
    CanonicalBrand,
    CanonicalProduct,
    LLMAnswer,
    Product,
    ProductAlias,
    ProductMention,
    Prompt,
    Run,
    Vertical,
)
from models.domain import PromptLanguage, RunStatus, Sentiment


def _create_run(db_session, vertical: Vertical, model_name: str = "qwen") -> Run:
    run = Run(vertical_id=vertical.id, provider="qwen", model_name=model_name, status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()
    return run


def _create_prompt_and_answer(db_session, vertical: Vertical, run: Run, prompt_text: str, answer_text: str) -> LLMAnswer:
    prompt = Prompt(vertical_id=vertical.id, run_id=run.id, text_zh=prompt_text, language_original=PromptLanguage.ZH)
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(run_id=run.id, prompt_id=prompt.id, provider="qwen", model_name=run.model_name, raw_answer_zh=answer_text)
    db_session.add(answer)
    db_session.flush()
    return answer


def _brand(db_session, vertical: Vertical, name: str, is_user_input: bool, aliases: dict | None = None) -> Brand:
    brand = Brand(
        vertical_id=vertical.id,
        display_name=name,
        original_name=name,
        translated_name=None,
        aliases=aliases or {"zh": [], "en": []},
        is_user_input=is_user_input,
    )
    db_session.add(brand)
    db_session.flush()
    return brand


def _mention(db_session, answer: LLMAnswer, brand: Brand, rank: int) -> None:
    db_session.add(
        BrandMention(
            llm_answer_id=answer.id,
            brand_id=brand.id,
            mentioned=True,
            rank=rank,
            sentiment=Sentiment.NEUTRAL,
            evidence_snippets={"zh": [brand.display_name], "en": []},
        )
    )
    db_session.flush()


def _product(db_session, vertical: Vertical, name: str) -> Product:
    product = Product(vertical_id=vertical.id, brand_id=None, display_name=name, original_name=name, translated_name=None, is_user_input=False)
    db_session.add(product)
    db_session.flush()
    return product


def _product_mention(db_session, answer: LLMAnswer, product: Product, rank: int) -> None:
    db_session.add(
        ProductMention(
            llm_answer_id=answer.id,
            product_id=product.id,
            mentioned=True,
            rank=rank,
            sentiment=Sentiment.NEUTRAL,
            evidence_snippets={"zh": [product.display_name], "en": []},
        )
    )
    db_session.flush()


def test_metrics_user_alias_wins_and_aggregates_under_display_name(client, db_session):
    vertical = Vertical(name="SUV Cars Mini", description="Mini")
    db_session.add(vertical)
    db_session.flush()

    run = _create_run(db_session, vertical)
    answer = _create_prompt_and_answer(db_session, vertical, run, "推荐家用SUV", "1. Volkswagen (大众)")

    vw = _brand(
        db_session,
        vertical,
        "VW",
        is_user_input=True,
        aliases={"zh": ["大众汽车", "一汽-大众", "上汽大众"], "en": ["VW", "Volkswagen"]},
    )
    discovered = _brand(db_session, vertical, "Volkswagen (大众)", is_user_input=False)

    _mention(db_session, answer, vw, rank=1)
    _mention(db_session, answer, discovered, rank=2)

    resp = client.get("/api/v1/metrics/latest", params={"vertical_id": vertical.id, "model_name": run.model_name})
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["brands"]) == 1
    assert data["brands"][0]["brand_id"] == vw.id
    assert data["brands"][0]["mention_rate"] == pytest.approx(1.0, rel=1e-6)


def test_metrics_dedupes_by_canonical_brand_alias(client, db_session):
    vertical = Vertical(name="Diapers", description="Diapers")
    db_session.add(vertical)
    db_session.flush()

    run = _create_run(db_session, vertical)
    answer = _create_prompt_and_answer(db_session, vertical, run, "推荐纸尿裤", "Unicharm")

    canonical = CanonicalBrand(vertical_id=vertical.id, canonical_name="Unicharm", display_name="Unicharm", mention_count=0)
    db_session.add(canonical)
    db_session.flush()
    db_session.add(BrandAlias(canonical_brand_id=canonical.id, alias="Unicharm (尤妮佳)"))
    db_session.flush()

    unicharm = _brand(db_session, vertical, "Unicharm", is_user_input=False)
    unicharm_zh = _brand(db_session, vertical, "Unicharm (尤妮佳)", is_user_input=False)

    _mention(db_session, answer, unicharm, rank=1)
    _mention(db_session, answer, unicharm_zh, rank=2)

    resp = client.get("/api/v1/metrics/latest", params={"vertical_id": vertical.id, "model_name": run.model_name})
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["brands"]) == 1
    assert data["brands"][0]["brand_id"] == unicharm.id
    assert data["brands"][0]["mention_rate"] == pytest.approx(1.0, rel=1e-6)


def test_metrics_dedupes_by_normalized_exact_fallback(client, db_session):
    vertical = Vertical(name="Diapers2", description="Diapers2")
    db_session.add(vertical)
    db_session.flush()

    run = _create_run(db_session, vertical)
    answer = _create_prompt_and_answer(db_session, vertical, run, "推荐纸尿裤", "Babycare")

    babycare = _brand(db_session, vertical, "Babycare", is_user_input=False)
    baby_care = _brand(db_session, vertical, "Baby Care", is_user_input=False)

    _mention(db_session, answer, babycare, rank=1)
    _mention(db_session, answer, baby_care, rank=2)

    resp = client.get("/api/v1/metrics/latest", params={"vertical_id": vertical.id, "model_name": run.model_name})
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["brands"]) == 1
    assert data["brands"][0]["brand_id"] == babycare.id


def test_metrics_always_returns_user_brands_and_hides_unmentioned_discovered(client, db_session):
    vertical = Vertical(name="Hiking Shoes", description="Hiking")
    db_session.add(vertical)
    db_session.flush()

    run = _create_run(db_session, vertical)
    _create_prompt_and_answer(db_session, vertical, run, "推荐徒步鞋", "No brands")

    user = _brand(db_session, vertical, "Salomon", is_user_input=True, aliases={"zh": ["萨洛蒙"], "en": ["Salomon"]})
    _brand(db_session, vertical, "Dick’s Sporting Goods", is_user_input=False)

    resp = client.get("/api/v1/metrics/latest", params={"vertical_id": vertical.id, "model_name": run.model_name})
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["brands"]) == 1
    assert data["brands"][0]["brand_id"] == user.id
    assert data["brands"][0]["mention_rate"] == pytest.approx(0.0, rel=1e-6)


def test_product_metrics_dedupes_by_canonical_product_alias(client, db_session):
    vertical = Vertical(name="Cars", description="Cars")
    db_session.add(vertical)
    db_session.flush()

    run = _create_run(db_session, vertical)
    answer = _create_prompt_and_answer(db_session, vertical, run, "推荐车型", "Goon")

    canonical = CanonicalProduct(vertical_id=vertical.id, canonical_name="Goon", display_name="Goon", mention_count=0)
    db_session.add(canonical)
    db_session.flush()
    db_session.add(ProductAlias(canonical_product_id=canonical.id, alias="Goo.n"))
    db_session.flush()

    goon = _product(db_session, vertical, "Goon")
    goon_variant = _product(db_session, vertical, "Goo.n")

    _product_mention(db_session, answer, goon, rank=1)
    _product_mention(db_session, answer, goon_variant, rank=2)

    resp = client.get("/api/v1/metrics/latest/products", params={"vertical_id": vertical.id, "model_name": run.model_name})
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["products"]) == 1
    assert data["products"][0]["product_id"] == goon.id
    assert data["products"][0]["mention_rate"] == pytest.approx(1.0, rel=1e-6)
