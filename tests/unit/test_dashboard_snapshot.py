from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductMention,
    Prompt,
    Run,
    RunMetrics,
    RunProductMetrics,
    Vertical,
)
from models.domain import PromptLanguage, RunStatus, Sentiment
from services.demo_dashboard_snapshot import build_dashboard_snapshot


def test_build_dashboard_snapshot_includes_dashboard_data(db_session: Session) -> None:
    vertical = _seed_dashboard_vertical(db_session)

    snapshot = build_dashboard_snapshot(db_session)

    assert snapshot.version == "1"
    assert len(snapshot.verticals) == 1

    vertical_snapshot = snapshot.verticals[0]
    assert vertical_snapshot.vertical.id == vertical.id
    assert vertical_snapshot.vertical.name == "SUV Cars"
    assert vertical_snapshot.available_models == ["qwen/qwen-2.5-72b-instruct"]
    assert [brand.display_name for brand in vertical_snapshot.user_brands] == ["Toyota"]

    assert vertical_snapshot.aggregate_brand_metrics is not None
    assert vertical_snapshot.aggregate_brand_metrics.model_name == "All Models"
    assert [brand.brand_name for brand in vertical_snapshot.aggregate_brand_metrics.brands] == [
        "Honda",
        "Toyota",
    ]

    assert vertical_snapshot.aggregate_product_metrics is not None
    assert [product.product_name for product in vertical_snapshot.aggregate_product_metrics.products] == [
        "CR-V",
        "RAV4",
    ]

    model_snapshot = vertical_snapshot.models[0]
    assert model_snapshot.model_name == "qwen/qwen-2.5-72b-instruct"
    assert model_snapshot.latest_run is not None
    assert model_snapshot.latest_run.model_name == "qwen/qwen-2.5-72b-instruct"
    assert model_snapshot.latest_brand_metrics is not None
    assert [metric.brand_name for metric in model_snapshot.latest_brand_metrics.metrics] == [
        "Toyota",
        "Honda",
    ]
    assert model_snapshot.latest_product_metrics is not None
    assert [metric.product_name for metric in model_snapshot.latest_product_metrics.products] == [
        "RAV4",
        "CR-V",
    ]


def _seed_dashboard_vertical(db_session: Session) -> Vertical:
    vertical = Vertical(name="SUV Cars", description="Sport Utility Vehicles")
    db_session.add(vertical)
    db_session.flush()

    toyota = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        translated_name=None,
        aliases={"en": ["Toyota"], "zh": ["丰田"]},
        is_user_input=True,
    )
    honda = Brand(
        vertical_id=vertical.id,
        display_name="Honda",
        original_name="Honda",
        translated_name=None,
        aliases={"en": ["Honda"], "zh": ["本田"]},
        is_user_input=False,
    )
    db_session.add_all([toyota, honda])
    db_session.flush()

    rav4 = Product(
        vertical_id=vertical.id,
        brand_id=toyota.id,
        display_name="RAV4",
        original_name="RAV4",
        translated_name=None,
        is_user_input=True,
    )
    crv = Product(
        vertical_id=vertical.id,
        brand_id=honda.id,
        display_name="CR-V",
        original_name="CR-V",
        translated_name=None,
        is_user_input=False,
    )
    db_session.add_all([rav4, crv])
    db_session.flush()

    run = Run(
        vertical_id=vertical.id,
        provider="openrouter",
        model_name="qwen/qwen-2.5-72b-instruct",
        status=RunStatus.COMPLETED,
        run_time=datetime(2026, 4, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    prompt = Prompt(
        vertical_id=vertical.id,
        run_id=run.id,
        text_en="Best SUVs in China?",
        text_zh="中国最好的SUV是什么？",
        language_original=PromptLanguage.EN,
    )
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider=run.provider,
        model_name=run.model_name,
        raw_answer_zh="丰田 RAV4 和本田 CR-V 都值得考虑。",
        raw_answer_en="Toyota RAV4 and Honda CR-V are both worth considering.",
    )
    db_session.add(answer)
    db_session.flush()

    db_session.add_all(
        [
            BrandMention(
                llm_answer_id=answer.id,
                brand_id=toyota.id,
                mentioned=True,
                rank=1,
                sentiment=Sentiment.POSITIVE,
                evidence_snippets={"zh": ["丰田 RAV4"], "en": ["Toyota RAV4"]},
            ),
            BrandMention(
                llm_answer_id=answer.id,
                brand_id=honda.id,
                mentioned=True,
                rank=2,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["本田 CR-V"], "en": ["Honda CR-V"]},
            ),
            ProductMention(
                llm_answer_id=answer.id,
                product_id=rav4.id,
                mentioned=True,
                rank=1,
                sentiment=Sentiment.POSITIVE,
                evidence_snippets={"zh": ["RAV4"], "en": ["RAV4"]},
            ),
            ProductMention(
                llm_answer_id=answer.id,
                product_id=crv.id,
                mentioned=True,
                rank=2,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["CR-V"], "en": ["CR-V"]},
            ),
            RunMetrics(
                run_id=run.id,
                brand_id=toyota.id,
                mention_rate=1.0,
                share_of_voice=0.6,
                top_spot_share=1.0,
                sentiment_index=1.0,
                dragon_lens_visibility=0.8,
            ),
            RunMetrics(
                run_id=run.id,
                brand_id=honda.id,
                mention_rate=1.0,
                share_of_voice=0.4,
                top_spot_share=0.0,
                sentiment_index=0.0,
                dragon_lens_visibility=0.3,
            ),
            RunProductMetrics(
                run_id=run.id,
                product_id=rav4.id,
                mention_rate=1.0,
                share_of_voice=0.6,
                top_spot_share=1.0,
                sentiment_index=1.0,
                dragon_lens_visibility=0.8,
            ),
            RunProductMetrics(
                run_id=run.id,
                product_id=crv.id,
                mention_rate=1.0,
                share_of_voice=0.4,
                top_spot_share=0.0,
                sentiment_index=0.0,
                dragon_lens_visibility=0.3,
            ),
        ]
    )
    db_session.commit()

    return vertical
