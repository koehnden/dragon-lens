import asyncio
from dataclasses import dataclass

import pytest

from models import ComparisonPrompt, ComparisonPromptSource, ComparisonPromptType, Run, RunStatus, Vertical
from services.comparison_prompts.run_pipeline import _fetch_one


@dataclass(frozen=True)
class _Resolution:
    route: object | None = None


class _Translator:
    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        return f"{target_lang}:{text}"

    def translate_text_sync(self, *args, **kwargs) -> str:
        raise RuntimeError("translate_text_sync must not be called inside async pipeline")


class _Router:
    async def query_with_resolution(self, resolution, prompt_zh: str):
        return "答案", 1, 2, 0.01


@pytest.mark.asyncio
async def test_fetch_one_uses_async_translation(db_session):
    vertical = Vertical(name="V", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    prompt = ComparisonPrompt(
        run_id=run.id,
        vertical_id=vertical.id,
        prompt_type=ComparisonPromptType.BRAND_VS_BRAND,
        source=ComparisonPromptSource.USER,
        text_en="Between A and B, which?",
        text_zh=None,
    )
    db_session.add(prompt)
    db_session.commit()
    db_session.refresh(prompt)
    sem = asyncio.Semaphore(1)
    answer = await _fetch_one(db_session, run, prompt, _Router(), _Resolution(), _Translator(), sem)
    assert answer and answer.raw_answer_en
