import pytest
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical
from models.domain import (
    BrandAlias,
    CanonicalBrand,
    RunStatus,
    Sentiment,
)
from services.metrics_service import (
    _build_brand_to_canonical_map,
    _to_metrics_with_canonical,
    recalculate_metrics_with_canonical,
)


class TestBuildBrandToCanonicalMap:

    def test_maps_canonical_names(self, db_session: Session):
        vertical = Vertical(name="Cars")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota",
        )
        db_session.add(canonical)
        db_session.flush()

        mapping = _build_brand_to_canonical_map(db_session, vertical.id)

        assert mapping["toyota"] == "Toyota"

    def test_maps_aliases(self, db_session: Session):
        vertical = Vertical(name="Cars2")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Volkswagen",
            display_name="Volkswagen",
        )
        db_session.add(canonical)
        db_session.flush()

        alias1 = BrandAlias(canonical_brand_id=canonical.id, alias="VW")
        alias2 = BrandAlias(canonical_brand_id=canonical.id, alias="大众")
        db_session.add_all([alias1, alias2])
        db_session.flush()

        mapping = _build_brand_to_canonical_map(db_session, vertical.id)

        assert mapping["volkswagen"] == "Volkswagen"
        assert mapping["vw"] == "Volkswagen"
        assert mapping["大众"] == "Volkswagen"

    def test_empty_vertical(self, db_session: Session):
        vertical = Vertical(name="Empty")
        db_session.add(vertical)
        db_session.flush()

        mapping = _build_brand_to_canonical_map(db_session, vertical.id)

        assert mapping == {}

    def test_multiple_canonicals(self, db_session: Session):
        vertical = Vertical(name="Multi")
        db_session.add(vertical)
        db_session.flush()

        canonical1 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota",
        )
        canonical2 = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Honda",
            display_name="Honda",
        )
        db_session.add_all([canonical1, canonical2])
        db_session.flush()

        mapping = _build_brand_to_canonical_map(db_session, vertical.id)

        assert mapping["toyota"] == "Toyota"
        assert mapping["honda"] == "Honda"


class TestToMetricsWithCanonical:

    def test_maps_mentions_to_canonical(self, db_session: Session):
        vertical = Vertical(name="Mapping Test")
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
            text_zh="Test",
            language_original="zh",
        )
        db_session.add(prompt)
        db_session.flush()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="VW is great",
        )
        db_session.add(answer)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
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
        db_session.flush()

        brand_to_canonical = {"vw": "Volkswagen"}

        metrics = _to_metrics_with_canonical([mention], brand_to_canonical)

        assert len(metrics) == 1
        assert metrics[0].brand == "Volkswagen"

    def test_keeps_original_if_no_mapping(self, db_session: Session):
        vertical = Vertical(name="No Mapping Test")
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
            text_zh="Test",
            language_original="zh",
        )
        db_session.add(prompt)
        db_session.flush()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="Toyota",
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
            sentiment=Sentiment.NEUTRAL,
        )
        db_session.add(mention)
        db_session.flush()

        brand_to_canonical = {}

        metrics = _to_metrics_with_canonical([mention], brand_to_canonical)

        assert len(metrics) == 1
        assert metrics[0].brand == "Toyota"

    def test_skips_unmentioned(self, db_session: Session):
        vertical = Vertical(name="Unmentioned Test")
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
            text_zh="Test",
            language_original="zh",
        )
        db_session.add(prompt)
        db_session.flush()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="Nothing",
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
            mentioned=False,
            rank=None,
            sentiment=Sentiment.NEUTRAL,
        )
        db_session.add(mention)
        db_session.flush()

        metrics = _to_metrics_with_canonical([mention], {})

        assert len(metrics) == 0


class TestRecalculateMetricsWithCanonical:

    def test_recalculate_with_canonical(self, db_session: Session):
        vertical = Vertical(name="Recalc Test")
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
            raw_answer_zh="VW and 大众 are great",
        )
        db_session.add(answer)
        db_session.flush()

        brand1 = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"zh": [], "en": []},
            is_user_input=True,
        )
        brand2 = Brand(
            vertical_id=vertical.id,
            display_name="大众",
            original_name="大众",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Volkswagen",
            display_name="Volkswagen",
            mention_count=10,
        )
        db_session.add(canonical)
        db_session.flush()

        alias1 = BrandAlias(canonical_brand_id=canonical.id, alias="VW")
        alias2 = BrandAlias(canonical_brand_id=canonical.id, alias="大众")
        db_session.add_all([alias1, alias2])
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
        db_session.commit()

        recalculate_metrics_with_canonical(db_session, run.id)

    def test_recalculate_skips_when_no_canonical(self, db_session: Session):
        vertical = Vertical(name="No Canonical Test")
        db_session.add(vertical)
        db_session.flush()

        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.COMPLETED,
        )
        db_session.add(run)
        db_session.commit()

        recalculate_metrics_with_canonical(db_session, run.id)

    def test_recalculate_run_not_found(self, db_session: Session):
        with pytest.raises(ValueError, match="not found"):
            recalculate_metrics_with_canonical(db_session, 99999)


class TestMetricsAggregation:

    def test_multiple_mentions_aggregate_to_canonical(self, db_session: Session):
        vertical = Vertical(name="Aggregation Test")
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

        prompt1 = Prompt(
            run_id=run.id,
            vertical_id=vertical.id,
            text_zh="第一个问题",
            language_original="zh",
        )
        prompt2 = Prompt(
            run_id=run.id,
            vertical_id=vertical.id,
            text_zh="第二个问题",
            language_original="zh",
        )
        db_session.add_all([prompt1, prompt2])
        db_session.flush()

        answer1 = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt1.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="VW is good",
        )
        answer2 = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt2.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            raw_answer_zh="大众 is good",
        )
        db_session.add_all([answer1, answer2])
        db_session.flush()

        brand1 = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"zh": [], "en": []},
            is_user_input=True,
        )
        brand2 = Brand(
            vertical_id=vertical.id,
            display_name="大众",
            original_name="大众",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        db_session.add_all([brand1, brand2])
        db_session.flush()

        mention1 = BrandMention(
            llm_answer_id=answer1.id,
            brand_id=brand1.id,
            mentioned=True,
            rank=1,
            sentiment=Sentiment.POSITIVE,
        )
        mention2 = BrandMention(
            llm_answer_id=answer2.id,
            brand_id=brand2.id,
            mentioned=True,
            rank=1,
            sentiment=Sentiment.POSITIVE,
        )
        db_session.add_all([mention1, mention2])
        db_session.flush()

        brand_to_canonical = {"vw": "Volkswagen", "大众": "Volkswagen"}

        metrics = _to_metrics_with_canonical([mention1, mention2], brand_to_canonical)

        assert len(metrics) == 2
        assert all(m.brand == "Volkswagen" for m in metrics)
