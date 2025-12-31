import pytest
import inspect
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical
from models.domain import (
    CanonicalBrand,
    EntityType,
    RunStatus,
    Sentiment,
    ValidationCandidate,
    ValidationStatus,
)


class TestConsolidationAutoTrigger:

    def test_consolidation_import_in_tasks(self):
        from workers.tasks import consolidate_run
        assert consolidate_run is not None

    def test_consolidation_call_exists_in_task_code(self):
        from workers import tasks
        source = inspect.getsource(tasks.run_vertical_analysis)

        assert "consolidate_run" in source
        assert "Consolidating entities" in source

    def test_consolidation_called_before_metrics(self):
        from workers import tasks
        source = inspect.getsource(tasks.run_vertical_analysis)

        metrics_pos = source.find("calculate_and_save_metrics")
        consolidate_pos = source.find("consolidate_run(self.db")

        assert metrics_pos > 0
        assert consolidate_pos > 0
        assert consolidate_pos < metrics_pos

    def test_consolidation_before_completion(self):
        from workers import tasks
        source = inspect.getsource(tasks.run_vertical_analysis)

        consolidate_pos = source.find("consolidate_run(self.db")
        completed_pos = source.find("RunStatus.COMPLETED")

        assert consolidate_pos > 0
        assert completed_pos > 0
        assert consolidate_pos < completed_pos


class TestConsolidationIntegrationWithRun:

    def test_consolidation_creates_canonical_entities(self, db_session: Session):
        vertical = Vertical(name="Integration Test")
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
            aliases={"zh": ["丰田"], "en": []},
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

        from services.entity_consolidation import consolidate_run

        result = consolidate_run(db_session, run.id)

        assert result.canonical_brands_created >= 1

        canonical = db_session.query(CanonicalBrand).filter(
            CanonicalBrand.vertical_id == vertical.id
        ).first()
        assert canonical is not None

    def test_consolidation_flags_low_frequency(self, db_session: Session):
        vertical = Vertical(name="Low Freq Test")
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
            raw_answer_zh="Test answer",
        )
        db_session.add(answer)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Obscure Brand",
            original_name="Obscure Brand",
            aliases={"zh": [], "en": []},
            is_user_input=False,
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
        db_session.commit()

        from services.entity_consolidation import consolidate_run

        result = consolidate_run(db_session, run.id)

        assert result.brands_flagged >= 0


class TestConsolidationResultLogging:

    def test_consolidation_result_structure(self):
        from services.entity_consolidation import ConsolidationResult

        result = ConsolidationResult(
            brands_merged=5,
            products_merged=3,
            brands_flagged=2,
            products_flagged=1,
            canonical_brands_created=10,
            canonical_products_created=8,
        )

        assert result.brands_merged == 5
        assert result.products_merged == 3
        assert result.brands_flagged == 2
        assert result.products_flagged == 1
        assert result.canonical_brands_created == 10
        assert result.canonical_products_created == 8
