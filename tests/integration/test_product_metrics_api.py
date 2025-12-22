import pytest
from datetime import datetime

from sqlalchemy.orm import Session

from models import (
    Base,
    Brand,
    LLMAnswer,
    Product,
    Prompt,
    Run,
    Vertical,
)
from models.domain import ProductMention, PromptLanguage, RunStatus, Sentiment


@pytest.fixture
def setup_product_metrics_data(db_session: Session):
    vertical = Vertical(name="SUV Cars", description="Sport Utility Vehicles")
    db_session.add(vertical)
    db_session.flush()

    toyota = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        translated_name="丰田",
        aliases={"zh": ["丰田"], "en": []},
    )
    honda = Brand(
        vertical_id=vertical.id,
        display_name="Honda",
        original_name="Honda",
        translated_name="本田",
        aliases={"zh": ["本田"], "en": []},
    )
    db_session.add_all([toyota, honda])
    db_session.flush()

    rav4 = Product(
        vertical_id=vertical.id,
        brand_id=toyota.id,
        display_name="RAV4",
        original_name="RAV4",
        translated_name="荣放",
    )
    camry = Product(
        vertical_id=vertical.id,
        brand_id=toyota.id,
        display_name="Camry",
        original_name="Camry",
        translated_name="凯美瑞",
    )
    crv = Product(
        vertical_id=vertical.id,
        brand_id=honda.id,
        display_name="CR-V",
        original_name="CR-V",
        translated_name=None,
    )
    db_session.add_all([rav4, camry, crv])
    db_session.flush()

    run = Run(
        vertical_id=vertical.id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
        run_time=datetime.utcnow(),
    )
    db_session.add(run)
    db_session.flush()

    prompt1 = Prompt(
        vertical_id=vertical.id,
        text_zh="推荐一款SUV",
        text_en="Recommend an SUV",
        language_original=PromptLanguage.ZH,
    )
    prompt2 = Prompt(
        vertical_id=vertical.id,
        text_zh="家用车推荐",
        text_en="Family car recommendation",
        language_original=PromptLanguage.ZH,
    )
    db_session.add_all([prompt1, prompt2])
    db_session.flush()

    answer1 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt1.id,
        raw_answer_zh="推荐RAV4和CR-V",
        raw_answer_en="Recommend RAV4 and CR-V",
    )
    answer2 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt2.id,
        raw_answer_zh="推荐凯美瑞",
        raw_answer_en="Recommend Camry",
    )
    db_session.add_all([answer1, answer2])
    db_session.flush()

    mention1 = ProductMention(
        llm_answer_id=answer1.id,
        product_id=rav4.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["RAV4"], "en": ["RAV4"]},
    )
    mention2 = ProductMention(
        llm_answer_id=answer1.id,
        product_id=crv.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["CR-V"], "en": ["CR-V"]},
    )
    mention3 = ProductMention(
        llm_answer_id=answer2.id,
        product_id=camry.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["凯美瑞"], "en": ["Camry"]},
    )
    db_session.add_all([mention1, mention2, mention3])
    db_session.commit()

    return {
        "vertical": vertical,
        "brands": {"toyota": toyota, "honda": honda},
        "products": {"rav4": rav4, "camry": camry, "crv": crv},
        "run": run,
    }


def test_get_latest_product_metrics(client, setup_product_metrics_data):
    data = setup_product_metrics_data
    vertical_id = data["vertical"].id

    response = client.get(
        "/api/v1/metrics/latest/products",
        params={"vertical_id": vertical_id, "model_name": "qwen"},
    )

    assert response.status_code == 200
    metrics = response.json()
    assert metrics["vertical_id"] == vertical_id
    assert metrics["model_name"] == "qwen"
    assert "products" in metrics
    assert len(metrics["products"]) == 3


def test_product_metrics_include_brand_name(client, setup_product_metrics_data):
    data = setup_product_metrics_data
    vertical_id = data["vertical"].id

    response = client.get(
        "/api/v1/metrics/latest/products",
        params={"vertical_id": vertical_id, "model_name": "qwen"},
    )

    assert response.status_code == 200
    metrics = response.json()

    product_names = {p["product_name"] for p in metrics["products"]}
    assert "RAV4" in product_names or "RAV4 (荣放)" in product_names

    for product in metrics["products"]:
        assert "brand_name" in product
        if "RAV4" in product["product_name"]:
            assert "Toyota" in product["brand_name"]


def test_product_metrics_aggregation(client, setup_product_metrics_data):
    data = setup_product_metrics_data
    vertical_id = data["vertical"].id

    response = client.get(
        "/api/v1/metrics/latest/products",
        params={"vertical_id": vertical_id, "model_name": "qwen"},
    )

    assert response.status_code == 200
    metrics = response.json()

    for product in metrics["products"]:
        assert "mention_rate" in product
        assert "share_of_voice" in product
        assert "top_spot_share" in product
        assert "sentiment_index" in product
        assert "dragon_lens_visibility" in product


def test_product_metrics_no_duplicates(client, setup_product_metrics_data):
    data = setup_product_metrics_data
    vertical_id = data["vertical"].id

    response = client.get(
        "/api/v1/metrics/latest/products",
        params={"vertical_id": vertical_id, "model_name": "qwen"},
    )

    assert response.status_code == 200
    metrics = response.json()

    product_ids = [p["product_id"] for p in metrics["products"]]
    assert len(product_ids) == len(set(product_ids))


def test_product_metrics_404_when_no_run(client, db_session):
    vertical = Vertical(name="Empty Vertical", description="No runs")
    db_session.add(vertical)
    db_session.commit()

    response = client.get(
        "/api/v1/metrics/latest/products",
        params={"vertical_id": vertical.id, "model_name": "qwen"},
    )

    assert response.status_code == 404
