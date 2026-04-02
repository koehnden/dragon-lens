from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    ComparisonAnswer,
    ComparisonPrompt,
    ComparisonRunEvent,
    ComparisonSentimentObservation,
    ConsolidationDebug,
    DailyMetrics,
    ExtractionDebug,
    LLMAnswer,
    LLMRoute,
    Product,
    ProductBrandMapping,
    ProductMention,
    Prompt,
    PromptLanguage,
    Run,
    RunComparisonConfig,
    RunMetrics,
    RunProductMetrics,
    RunStatus,
    Sentiment,
    Vertical,
)
from models.admin_schemas import (
    DemoAnswerPayload,
    DemoBrandMentionPayload,
    DemoBrandPayload,
    DemoProductBrandMappingPayload,
    DemoProductMentionPayload,
    DemoProductPayload,
    DemoPromptPayload,
    DemoPublishRequest,
    DemoRunMetricPayload,
    DemoRunPayload,
    DemoRunProductMetricPayload,
    DemoVerticalPayload,
)


def build_demo_publish_request(
    db: Session,
    vertical_id: int,
    submission_id: str,
    source_app_version: str | None = None,
) -> DemoPublishRequest:
    vertical = _vertical_or_raise(db, vertical_id)
    runs = _completed_runs(db, vertical_id)
    run_ids = [run.id for run in runs]
    prompts = _prompts_for_runs(db, run_ids)
    prompt_ids = [prompt.id for prompt in prompts]
    answers = _answers_for_runs(db, run_ids)
    answer_ids = [answer.id for answer in answers]
    return DemoPublishRequest(
        submission_id=submission_id,
        source_app_version=source_app_version,
        published_at=datetime.now(timezone.utc),
        vertical=DemoVerticalPayload(
            name=vertical.name, description=vertical.description
        ),
        brands=_brand_payloads(db, vertical_id),
        products=_product_payloads(db, vertical_id),
        runs=[_run_payload(run) for run in runs],
        prompts=[
            _prompt_payload(prompt) for prompt in prompts if prompt.id in prompt_ids
        ],
        answers=[_answer_payload(answer) for answer in answers],
        brand_mentions=_brand_mentions_payloads(db, answer_ids),
        product_mentions=_product_mentions_payloads(db, answer_ids),
        product_brand_mappings=_mapping_payloads(db, vertical_id),
        run_metrics=_run_metrics_payloads(db, run_ids),
        run_product_metrics=_run_product_metrics_payloads(db, run_ids),
    )


def apply_demo_publish_request(
    db: Session,
    payload: DemoPublishRequest,
) -> tuple[int, int, int, int]:
    existing = db.query(Vertical).filter(Vertical.name == payload.vertical.name).first()
    if existing:
        _delete_vertical_snapshot(db, existing.id)
        db.flush()
        db.expunge_all()
    vertical = Vertical(
        name=payload.vertical.name, description=payload.vertical.description
    )
    db.add(vertical)
    db.flush()
    brands = _create_brands(db, vertical.id, payload.brands)
    products = _create_products(db, vertical.id, payload.products, brands)
    runs = _create_runs(db, vertical.id, payload.runs)
    prompts = _create_prompts(db, vertical.id, payload.prompts, runs)
    answers = _create_answers(db, payload.answers, runs, prompts)
    _create_brand_mentions(db, payload.brand_mentions, answers, brands)
    _create_product_mentions(db, payload.product_mentions, answers, products)
    _create_mappings(db, vertical.id, payload.product_brand_mappings, products, brands)
    _create_run_metrics(db, payload.run_metrics, runs, brands)
    _create_run_product_metrics(db, payload.run_product_metrics, runs, products)
    return vertical.id, len(runs), len(brands), len(products)


def _vertical_or_raise(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise ValueError(f"Vertical {vertical_id} not found")
    return vertical


def _completed_runs(db: Session, vertical_id: int) -> list[Run]:
    return (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.status == RunStatus.COMPLETED,
        )
        .order_by(Run.run_time.asc(), Run.id.asc())
        .all()
    )


def _prompts_for_runs(db: Session, run_ids: list[int]) -> list[Prompt]:
    if not run_ids:
        return []
    return (
        db.query(Prompt)
        .filter(Prompt.run_id.in_(run_ids))
        .order_by(Prompt.id.asc())
        .all()
    )


def _answers_for_runs(db: Session, run_ids: list[int]) -> list[LLMAnswer]:
    if not run_ids:
        return []
    return (
        db.query(LLMAnswer)
        .filter(LLMAnswer.run_id.in_(run_ids))
        .order_by(LLMAnswer.id.asc())
        .all()
    )


def _brand_payloads(db: Session, vertical_id: int) -> list[DemoBrandPayload]:
    rows = (
        db.query(Brand)
        .filter(Brand.vertical_id == vertical_id)
        .order_by(Brand.id.asc())
        .all()
    )
    return [
        DemoBrandPayload(
            source_id=row.id,
            display_name=row.display_name,
            original_name=row.original_name,
            translated_name=row.translated_name,
            aliases=row.aliases or {},
            is_user_input=row.is_user_input,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _product_payloads(db: Session, vertical_id: int) -> list[DemoProductPayload]:
    rows = (
        db.query(Product)
        .filter(Product.vertical_id == vertical_id)
        .order_by(Product.id.asc())
        .all()
    )
    return [
        DemoProductPayload(
            source_id=row.id,
            brand_source_id=row.brand_id,
            display_name=row.display_name,
            original_name=row.original_name,
            translated_name=row.translated_name,
            is_user_input=row.is_user_input,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _run_payload(run: Run) -> DemoRunPayload:
    return DemoRunPayload(
        source_id=run.id,
        provider=run.provider,
        model_name=run.model_name,
        route=run.route.value if run.route else None,
        status=run.status.value,
        reuse_answers=run.reuse_answers,
        web_search_enabled=run.web_search_enabled,
        run_time=run.run_time,
        completed_at=run.completed_at,
        error_message=run.error_message,
    )


def _prompt_payload(prompt: Prompt) -> DemoPromptPayload:
    return DemoPromptPayload(
        source_id=prompt.id,
        run_source_id=prompt.run_id or 0,
        text_en=prompt.text_en,
        text_zh=prompt.text_zh,
        language_original=prompt.language_original.value,
        created_at=prompt.created_at,
    )


def _answer_payload(answer: LLMAnswer) -> DemoAnswerPayload:
    return DemoAnswerPayload(
        source_id=answer.id,
        run_source_id=answer.run_id,
        prompt_source_id=answer.prompt_id,
        provider=answer.provider,
        model_name=answer.model_name,
        route=answer.route.value if answer.route else None,
        raw_answer_zh=answer.raw_answer_zh,
        raw_answer_en=answer.raw_answer_en,
        tokens_in=answer.tokens_in,
        tokens_out=answer.tokens_out,
        latency=answer.latency,
        cost_estimate=answer.cost_estimate,
        created_at=answer.created_at,
    )


def _brand_mentions_payloads(
    db: Session,
    answer_ids: list[int],
) -> list[DemoBrandMentionPayload]:
    if not answer_ids:
        return []
    rows = (
        db.query(BrandMention)
        .filter(BrandMention.llm_answer_id.in_(answer_ids))
        .order_by(BrandMention.id.asc())
        .all()
    )
    return [
        DemoBrandMentionPayload(
            llm_answer_source_id=row.llm_answer_id,
            brand_source_id=row.brand_id,
            mentioned=row.mentioned,
            rank=row.rank,
            sentiment=row.sentiment.value,
            evidence_snippets=row.evidence_snippets or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


def _product_mentions_payloads(
    db: Session,
    answer_ids: list[int],
) -> list[DemoProductMentionPayload]:
    if not answer_ids:
        return []
    rows = (
        db.query(ProductMention)
        .filter(ProductMention.llm_answer_id.in_(answer_ids))
        .order_by(ProductMention.id.asc())
        .all()
    )
    return [
        DemoProductMentionPayload(
            llm_answer_source_id=row.llm_answer_id,
            product_source_id=row.product_id,
            mentioned=row.mentioned,
            rank=row.rank,
            sentiment=row.sentiment.value,
            evidence_snippets=row.evidence_snippets or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


def _mapping_payloads(
    db: Session, vertical_id: int
) -> list[DemoProductBrandMappingPayload]:
    rows = (
        db.query(ProductBrandMapping)
        .filter(ProductBrandMapping.vertical_id == vertical_id)
        .order_by(ProductBrandMapping.id.asc())
        .all()
    )
    return [
        DemoProductBrandMappingPayload(
            product_source_id=row.product_id,
            brand_source_id=row.brand_id,
            confidence=row.confidence,
            is_validated=row.is_validated,
            source=row.source,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def _run_metrics_payloads(
    db: Session, run_ids: list[int]
) -> list[DemoRunMetricPayload]:
    if not run_ids:
        return []
    rows = (
        db.query(RunMetrics)
        .filter(RunMetrics.run_id.in_(run_ids))
        .order_by(RunMetrics.id.asc())
        .all()
    )
    return [
        DemoRunMetricPayload(
            run_source_id=row.run_id,
            brand_source_id=row.brand_id,
            mention_rate=row.mention_rate,
            share_of_voice=row.share_of_voice,
            top_spot_share=row.top_spot_share,
            sentiment_index=row.sentiment_index,
            dragon_lens_visibility=row.dragon_lens_visibility,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _run_product_metrics_payloads(
    db: Session,
    run_ids: list[int],
) -> list[DemoRunProductMetricPayload]:
    if not run_ids:
        return []
    rows = (
        db.query(RunProductMetrics)
        .filter(RunProductMetrics.run_id.in_(run_ids))
        .order_by(RunProductMetrics.id.asc())
        .all()
    )
    return [
        DemoRunProductMetricPayload(
            run_source_id=row.run_id,
            product_source_id=row.product_id,
            mention_rate=row.mention_rate,
            share_of_voice=row.share_of_voice,
            top_spot_share=row.top_spot_share,
            sentiment_index=row.sentiment_index,
            dragon_lens_visibility=row.dragon_lens_visibility,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _delete_vertical_snapshot(db: Session, vertical_id: int) -> None:
    run_ids = _ids(db.query(Run.id).filter(Run.vertical_id == vertical_id).all())
    answer_ids = (
        _ids(db.query(LLMAnswer.id).filter(LLMAnswer.run_id.in_(run_ids)).all())
        if run_ids
        else []
    )
    _delete_comparison_rows(db, run_ids)
    if answer_ids:
        db.query(ExtractionDebug).filter(
            ExtractionDebug.llm_answer_id.in_(answer_ids)
        ).delete(synchronize_session=False)
        db.query(BrandMention).filter(
            BrandMention.llm_answer_id.in_(answer_ids)
        ).delete(synchronize_session=False)
        db.query(ProductMention).filter(
            ProductMention.llm_answer_id.in_(answer_ids)
        ).delete(synchronize_session=False)
    if run_ids:
        db.query(ConsolidationDebug).filter(
            ConsolidationDebug.run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.query(RunMetrics).filter(RunMetrics.run_id.in_(run_ids)).delete(
            synchronize_session=False
        )
        db.query(RunProductMetrics).filter(
            RunProductMetrics.run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.query(LLMAnswer).filter(LLMAnswer.run_id.in_(run_ids)).delete(
            synchronize_session=False
        )
        db.query(Run).filter(Run.id.in_(run_ids)).delete(synchronize_session=False)
    db.query(ProductBrandMapping).filter(
        ProductBrandMapping.vertical_id == vertical_id
    ).delete(synchronize_session=False)
    db.query(Product).filter(Product.vertical_id == vertical_id).delete(
        synchronize_session=False
    )
    db.query(Brand).filter(Brand.vertical_id == vertical_id).delete(
        synchronize_session=False
    )
    db.query(Prompt).filter(Prompt.vertical_id == vertical_id).delete(
        synchronize_session=False
    )
    db.query(DailyMetrics).filter(DailyMetrics.vertical_id == vertical_id).delete(
        synchronize_session=False
    )
    db.query(Vertical).filter(Vertical.id == vertical_id).delete(
        synchronize_session=False
    )


def _delete_comparison_rows(db: Session, run_ids: list[int]) -> None:
    if not run_ids:
        return
    answer_ids = _ids(
        db.query(ComparisonAnswer.id).filter(ComparisonAnswer.run_id.in_(run_ids)).all()
    )
    if answer_ids:
        db.query(ComparisonSentimentObservation).filter(
            ComparisonSentimentObservation.comparison_answer_id.in_(answer_ids)
        ).delete(synchronize_session=False)
    db.query(ComparisonRunEvent).filter(ComparisonRunEvent.run_id.in_(run_ids)).delete(
        synchronize_session=False
    )
    db.query(ComparisonAnswer).filter(ComparisonAnswer.run_id.in_(run_ids)).delete(
        synchronize_session=False
    )
    db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id.in_(run_ids)).delete(
        synchronize_session=False
    )
    db.query(RunComparisonConfig).filter(
        RunComparisonConfig.run_id.in_(run_ids)
    ).delete(synchronize_session=False)


def _ids(rows: list[tuple[int]]) -> list[int]:
    return [int(row[0]) for row in rows]


def _create_brands(
    db: Session, vertical_id: int, payloads: list[DemoBrandPayload]
) -> dict[int, Brand]:
    created: dict[int, Brand] = {}
    for payload in payloads:
        brand = Brand(
            vertical_id=vertical_id,
            display_name=payload.display_name,
            original_name=payload.original_name,
            translated_name=payload.translated_name,
            aliases=payload.aliases,
            is_user_input=payload.is_user_input,
            created_at=payload.created_at,
        )
        db.add(brand)
        db.flush()
        created[payload.source_id] = brand
    return created


def _create_products(
    db: Session,
    vertical_id: int,
    payloads: list[DemoProductPayload],
    brands: dict[int, Brand],
) -> dict[int, Product]:
    created: dict[int, Product] = {}
    for payload in payloads:
        brand = brands.get(payload.brand_source_id or -1)
        product = Product(
            vertical_id=vertical_id,
            brand_id=brand.id if brand else None,
            display_name=payload.display_name,
            original_name=payload.original_name,
            translated_name=payload.translated_name,
            is_user_input=payload.is_user_input,
            created_at=payload.created_at,
        )
        db.add(product)
        db.flush()
        created[payload.source_id] = product
    return created


def _create_runs(
    db: Session, vertical_id: int, payloads: list[DemoRunPayload]
) -> dict[int, Run]:
    created: dict[int, Run] = {}
    for payload in payloads:
        run = Run(
            vertical_id=vertical_id,
            provider=payload.provider,
            model_name=payload.model_name,
            route=_route(payload.route),
            status=RunStatus(payload.status),
            reuse_answers=payload.reuse_answers,
            web_search_enabled=payload.web_search_enabled,
            run_time=payload.run_time,
            completed_at=payload.completed_at,
            error_message=payload.error_message,
        )
        db.add(run)
        db.flush()
        created[payload.source_id] = run
    return created


def _route(value: str | None) -> LLMRoute | None:
    return None if value is None else LLMRoute(value)


def _create_prompts(
    db: Session,
    vertical_id: int,
    payloads: list[DemoPromptPayload],
    runs: dict[int, Run],
) -> dict[int, Prompt]:
    created: dict[int, Prompt] = {}
    for payload in payloads:
        run = runs.get(payload.run_source_id)
        if not run:
            continue
        prompt = Prompt(
            vertical_id=vertical_id,
            run_id=run.id,
            text_en=payload.text_en,
            text_zh=payload.text_zh,
            language_original=PromptLanguage(payload.language_original),
            created_at=payload.created_at,
        )
        db.add(prompt)
        db.flush()
        created[payload.source_id] = prompt
    return created


def _create_answers(
    db: Session,
    payloads: list[DemoAnswerPayload],
    runs: dict[int, Run],
    prompts: dict[int, Prompt],
) -> dict[int, LLMAnswer]:
    created: dict[int, LLMAnswer] = {}
    for payload in payloads:
        run = runs.get(payload.run_source_id)
        prompt = prompts.get(payload.prompt_source_id)
        if not run or not prompt:
            continue
        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider=payload.provider,
            model_name=payload.model_name,
            route=_route(payload.route),
            raw_answer_zh=payload.raw_answer_zh,
            raw_answer_en=payload.raw_answer_en,
            tokens_in=payload.tokens_in,
            tokens_out=payload.tokens_out,
            latency=payload.latency,
            cost_estimate=payload.cost_estimate,
            created_at=payload.created_at,
        )
        db.add(answer)
        db.flush()
        created[payload.source_id] = answer
    return created


def _create_brand_mentions(
    db: Session,
    payloads: list[DemoBrandMentionPayload],
    answers: dict[int, LLMAnswer],
    brands: dict[int, Brand],
) -> None:
    for payload in payloads:
        answer = answers.get(payload.llm_answer_source_id)
        brand = brands.get(payload.brand_source_id)
        if not answer or not brand:
            continue
        db.add(
            BrandMention(
                llm_answer_id=answer.id,
                brand_id=brand.id,
                mentioned=payload.mentioned,
                rank=payload.rank,
                sentiment=Sentiment(payload.sentiment),
                evidence_snippets=payload.evidence_snippets,
                created_at=payload.created_at,
            )
        )


def _create_product_mentions(
    db: Session,
    payloads: list[DemoProductMentionPayload],
    answers: dict[int, LLMAnswer],
    products: dict[int, Product],
) -> None:
    for payload in payloads:
        answer = answers.get(payload.llm_answer_source_id)
        product = products.get(payload.product_source_id)
        if not answer or not product:
            continue
        db.add(
            ProductMention(
                llm_answer_id=answer.id,
                product_id=product.id,
                mentioned=payload.mentioned,
                rank=payload.rank,
                sentiment=Sentiment(payload.sentiment),
                evidence_snippets=payload.evidence_snippets,
                created_at=payload.created_at,
            )
        )


def _create_mappings(
    db: Session,
    vertical_id: int,
    payloads: list[DemoProductBrandMappingPayload],
    products: dict[int, Product],
    brands: dict[int, Brand],
) -> None:
    for payload in payloads:
        product = products.get(payload.product_source_id or -1)
        brand = brands.get(payload.brand_source_id or -1)
        if not product and not brand:
            continue
        db.add(
            ProductBrandMapping(
                vertical_id=vertical_id,
                product_id=product.id if product else None,
                brand_id=brand.id if brand else None,
                confidence=payload.confidence,
                is_validated=payload.is_validated,
                source=payload.source,
                created_at=payload.created_at,
                updated_at=payload.updated_at,
            )
        )


def _create_run_metrics(
    db: Session,
    payloads: list[DemoRunMetricPayload],
    runs: dict[int, Run],
    brands: dict[int, Brand],
) -> None:
    for payload in payloads:
        run = runs.get(payload.run_source_id)
        brand = brands.get(payload.brand_source_id)
        if not run or not brand:
            continue
        db.add(
            RunMetrics(
                run_id=run.id,
                brand_id=brand.id,
                mention_rate=payload.mention_rate,
                share_of_voice=payload.share_of_voice,
                top_spot_share=payload.top_spot_share,
                sentiment_index=payload.sentiment_index,
                dragon_lens_visibility=payload.dragon_lens_visibility,
                created_at=payload.created_at,
            )
        )


def _create_run_product_metrics(
    db: Session,
    payloads: list[DemoRunProductMetricPayload],
    runs: dict[int, Run],
    products: dict[int, Product],
) -> None:
    for payload in payloads:
        run = runs.get(payload.run_source_id)
        product = products.get(payload.product_source_id)
        if not run or not product:
            continue
        db.add(
            RunProductMetrics(
                run_id=run.id,
                product_id=product.id,
                mention_rate=payload.mention_rate,
                share_of_voice=payload.share_of_voice,
                top_spot_share=payload.top_spot_share,
                sentiment_index=payload.sentiment_index,
                dragon_lens_visibility=payload.dragon_lens_visibility,
                created_at=payload.created_at,
            )
        )
