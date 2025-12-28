"""Tests for run-prompt association and answer reuse logic.

These tests verify:
1. Prompts are associated with specific runs (via run_id)
2. Answer reuse is controlled by run.reuse_answers flag
3. Answer matching considers provider, model_name, and web_search_enabled
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Brand, LLMAnswer, Prompt, Run, Vertical
from models.domain import PromptLanguage, RunStatus


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def vertical(db_session):
    v = Vertical(name="SUV Cars", description="SUV recommendations")
    db_session.add(v)
    db_session.commit()
    return v


class TestPromptRunAssociation:

    def test_prompt_has_run_id_field(self, db_session, vertical):
        """Prompt model should have run_id field."""
        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.PENDING,
        )
        db_session.add(run)
        db_session.commit()

        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh="推荐SUV",
            text_en="Recommend SUV",
            language_original=PromptLanguage.ZH,
        )
        db_session.add(prompt)
        db_session.commit()

        assert prompt.run_id == run.id

    def test_run_has_prompts_relationship(self, db_session, vertical):
        """Run should have a prompts relationship."""
        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.PENDING,
        )
        db_session.add(run)
        db_session.commit()

        prompt1 = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh="推荐SUV",
            text_en="Recommend SUV",
            language_original=PromptLanguage.ZH,
        )
        prompt2 = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh="比较品牌",
            text_en="Compare brands",
            language_original=PromptLanguage.ZH,
        )
        db_session.add_all([prompt1, prompt2])
        db_session.commit()

        db_session.refresh(run)
        assert len(run.prompts) == 2

    def test_prompts_isolated_per_run(self, db_session, vertical):
        """Each run should only see its own prompts."""
        run1 = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.COMPLETED,
        )
        run2 = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
        )
        db_session.add_all([run1, run2])
        db_session.commit()

        prompt1 = Prompt(
            vertical_id=vertical.id,
            run_id=run1.id,
            text_zh="推荐SUV",
            text_en="Recommend SUV",
            language_original=PromptLanguage.ZH,
        )
        prompt2 = Prompt(
            vertical_id=vertical.id,
            run_id=run2.id,
            text_zh="推荐SUV",
            text_en="Recommend SUV",
            language_original=PromptLanguage.ZH,
        )
        db_session.add_all([prompt1, prompt2])
        db_session.commit()

        run1_prompts = db_session.query(Prompt).filter(Prompt.run_id == run1.id).all()
        run2_prompts = db_session.query(Prompt).filter(Prompt.run_id == run2.id).all()

        assert len(run1_prompts) == 1
        assert len(run2_prompts) == 1
        assert run1_prompts[0].id != run2_prompts[0].id


class TestRunReuseAnswersFlag:

    def test_run_has_reuse_answers_field(self, db_session, vertical):
        """Run model should have reuse_answers field."""
        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(run)
        db_session.commit()

        assert run.reuse_answers is True

    def test_run_reuse_answers_defaults_to_false(self, db_session, vertical):
        """reuse_answers should default to False for production safety."""
        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.PENDING,
        )
        db_session.add(run)
        db_session.commit()

        assert run.reuse_answers is False

    def test_run_has_web_search_enabled_field(self, db_session, vertical):
        """Run model should have web_search_enabled field."""
        run = Run(
            vertical_id=vertical.id,
            provider="kimi",
            model_name="moonshot-v1-8k",
            status=RunStatus.PENDING,
            web_search_enabled=True,
        )
        db_session.add(run)
        db_session.commit()

        assert run.web_search_enabled is True

    def test_run_web_search_enabled_defaults_to_false(self, db_session, vertical):
        """web_search_enabled should default to False."""
        run = Run(
            vertical_id=vertical.id,
            provider="qwen",
            model_name="qwen2.5:7b",
            status=RunStatus.PENDING,
        )
        db_session.add(run)
        db_session.commit()

        assert run.web_search_enabled is False


class TestAnswerReuseLogic:

    def _create_completed_run_with_answer(
        self,
        db_session,
        vertical,
        provider: str,
        model_name: str,
        prompt_text_zh: str,
        answer_text: str,
        web_search_enabled: bool = False,
    ):
        """Helper to create a completed run with an answer."""
        run = Run(
            vertical_id=vertical.id,
            provider=provider,
            model_name=model_name,
            status=RunStatus.COMPLETED,
            web_search_enabled=web_search_enabled,
            completed_at=datetime.utcnow(),
        )
        db_session.add(run)
        db_session.commit()

        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh=prompt_text_zh,
            text_en="",
            language_original=PromptLanguage.ZH,
        )
        db_session.add(prompt)
        db_session.commit()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider=provider,
            model_name=model_name,
            raw_answer_zh=answer_text,
            raw_answer_en="",
            tokens_in=100,
            tokens_out=200,
        )
        db_session.add(answer)
        db_session.commit()

        return run, prompt, answer

    def test_no_reuse_when_reuse_answers_is_false(self, db_session, vertical):
        """When reuse_answers=False, should NOT reuse existing answers."""
        from services.answer_reuse import find_reusable_answer

        self._create_completed_run_with_answer(
            db_session, vertical,
            provider="deepseek",
            model_name="deepseek-chat",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=False,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is None

    def test_reuse_when_reuse_answers_is_true_and_match_found(self, db_session, vertical):
        """When reuse_answers=True and matching answer exists, should return it."""
        from services.answer_reuse import find_reusable_answer

        _, _, original_answer = self._create_completed_run_with_answer(
            db_session, vertical,
            provider="deepseek",
            model_name="deepseek-chat",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is not None
        assert result.raw_answer_zh == "1. 丰田RAV4..."

    def test_no_reuse_when_provider_differs(self, db_session, vertical):
        """Should NOT reuse answer from different provider."""
        from services.answer_reuse import find_reusable_answer

        self._create_completed_run_with_answer(
            db_session, vertical,
            provider="deepseek",
            model_name="deepseek-chat",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="kimi",
            model_name="moonshot-v1-8k",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is None

    def test_no_reuse_when_model_differs(self, db_session, vertical):
        """Should NOT reuse answer from different model."""
        from services.answer_reuse import find_reusable_answer

        self._create_completed_run_with_answer(
            db_session, vertical,
            provider="deepseek",
            model_name="deepseek-chat",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-reasoner",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is None

    def test_no_reuse_when_web_search_differs(self, db_session, vertical):
        """Should NOT reuse answer when web_search_enabled differs."""
        from services.answer_reuse import find_reusable_answer

        self._create_completed_run_with_answer(
            db_session, vertical,
            provider="kimi",
            model_name="moonshot-v1-8k",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
            web_search_enabled=False,
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="kimi",
            model_name="moonshot-v1-8k",
            status=RunStatus.PENDING,
            reuse_answers=True,
            web_search_enabled=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is None

    def test_no_reuse_from_incomplete_run(self, db_session, vertical):
        """Should NOT reuse answer from run that is not COMPLETED."""
        from services.answer_reuse import find_reusable_answer

        run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.IN_PROGRESS,
        )
        db_session.add(run)
        db_session.commit()

        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh="推荐10款SUV",
            text_en="",
            language_original=PromptLanguage.ZH,
        )
        db_session.add(prompt)
        db_session.commit()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="deepseek",
            model_name="deepseek-chat",
            raw_answer_zh="1. 丰田RAV4...",
            raw_answer_en="",
            tokens_in=100,
            tokens_out=200,
        )
        db_session.add(answer)
        db_session.commit()

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is None

    def test_no_reuse_when_prompt_text_differs(self, db_session, vertical):
        """Should NOT reuse answer when prompt text doesn't match."""
        from services.answer_reuse import find_reusable_answer

        self._create_completed_run_with_answer(
            db_session, vertical,
            provider="deepseek",
            model_name="deepseek-chat",
            prompt_text_zh="推荐10款SUV",
            answer_text="1. 丰田RAV4...",
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐5款电动SUV",
        )

        assert result is None

    def test_reuse_with_web_search_enabled_matching(self, db_session, vertical):
        """Should reuse answer when web_search_enabled matches (both True)."""
        from services.answer_reuse import find_reusable_answer

        _, _, original_answer = self._create_completed_run_with_answer(
            db_session, vertical,
            provider="kimi",
            model_name="moonshot-v1-8k",
            prompt_text_zh="推荐10款SUV",
            answer_text="Based on web search: 1. 丰田RAV4...",
            web_search_enabled=True,
        )

        new_run = Run(
            vertical_id=vertical.id,
            provider="kimi",
            model_name="moonshot-v1-8k",
            status=RunStatus.PENDING,
            reuse_answers=True,
            web_search_enabled=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_zh="推荐10款SUV",
        )

        assert result is not None
        assert result.raw_answer_zh == "Based on web search: 1. 丰田RAV4..."

    def test_reuse_english_only_prompt(self, db_session, vertical):
        """Should reuse answer when matching on English text only."""
        from services.answer_reuse import find_reusable_answer

        run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.COMPLETED,
            completed_at=datetime.utcnow(),
        )
        db_session.add(run)
        db_session.commit()

        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh=None,
            text_en="Recommend 10 SUVs",
            language_original=PromptLanguage.EN,
        )
        db_session.add(prompt)
        db_session.commit()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="deepseek",
            model_name="deepseek-chat",
            raw_answer_zh="1. Toyota RAV4...",
            raw_answer_en="1. Toyota RAV4...",
            tokens_in=100,
            tokens_out=200,
        )
        db_session.add(answer)
        db_session.commit()

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_en="Recommend 10 SUVs",
        )

        assert result is not None
        assert result.raw_answer_zh == "1. Toyota RAV4..."

    def test_reuse_matches_either_zh_or_en(self, db_session, vertical):
        """Should find match when either Chinese or English text matches."""
        from services.answer_reuse import find_reusable_answer

        run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.COMPLETED,
            completed_at=datetime.utcnow(),
        )
        db_session.add(run)
        db_session.commit()

        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_zh="推荐10款SUV",
            text_en="Recommend 10 SUVs",
            language_original=PromptLanguage.ZH,
        )
        db_session.add(prompt)
        db_session.commit()

        answer = LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="deepseek",
            model_name="deepseek-chat",
            raw_answer_zh="1. Toyota RAV4...",
            raw_answer_en="1. Toyota RAV4...",
            tokens_in=100,
            tokens_out=200,
        )
        db_session.add(answer)
        db_session.commit()

        new_run = Run(
            vertical_id=vertical.id,
            provider="deepseek",
            model_name="deepseek-chat",
            status=RunStatus.PENDING,
            reuse_answers=True,
        )
        db_session.add(new_run)
        db_session.commit()

        result = find_reusable_answer(
            db=db_session,
            run=new_run,
            prompt_text_en="Recommend 10 SUVs",
        )

        assert result is not None
        assert result.raw_answer_zh == "1. Toyota RAV4..."
