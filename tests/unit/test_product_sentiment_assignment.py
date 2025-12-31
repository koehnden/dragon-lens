from datetime import datetime

import pytest


class DummyTranslator:
    def translate_text_sync(self, text: str, source_lang: str, target_lang: str) -> str:
        return text


class StubOllama:
    async def extract_products(self, text_zh, product_names, product_aliases, brand_names, brand_aliases):
        return [
            {"product_index": 0, "mentioned": True, "snippets": ["RAV4很好"], "rank": 1},
        ]

    async def classify_sentiment(self, text_zh: str) -> str:
        return "positive"


def _build_answer(db_session, vertical_id: int, text_zh: str):
    from models import LLMAnswer, Prompt, PromptLanguage, Run, RunStatus

    run = Run(vertical_id=vertical_id, model_name="qwen", status=RunStatus.COMPLETED, run_time=datetime.utcnow())
    db_session.add(run)
    db_session.flush()

    prompt = Prompt(vertical_id=vertical_id, text_zh="test", text_en="test", language_original=PromptLanguage.ZH)
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider="qwen",
        model_name="qwen",
        raw_answer_zh=text_zh,
        raw_answer_en="",
    )
    db_session.add(answer)
    db_session.flush()
    return answer


def test_create_product_mentions_sets_sentiment_from_first_snippet(db_session):
    from models import Brand, Product, ProductMention, Sentiment, Vertical
    from workers.tasks import _create_product_mentions

    vertical = Vertical(name="SUV Cars", description="test")
    db_session.add(vertical)
    db_session.flush()

    brand = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db_session.add(brand)
    db_session.flush()

    product = Product(
        vertical_id=vertical.id,
        brand_id=brand.id,
        display_name="RAV4",
        original_name="RAV4",
        translated_name=None,
    )
    db_session.add(product)
    db_session.flush()

    answer = _build_answer(db_session, vertical.id, "RAV4很好")

    _create_product_mentions(
        db_session,
        answer,
        [product],
        answer.raw_answer_zh,
        DummyTranslator(),
        [brand],
        StubOllama(),
    )
    db_session.commit()

    mention = db_session.query(ProductMention).filter(ProductMention.llm_answer_id == answer.id).one()
    assert mention.rank == 1
    assert mention.sentiment == Sentiment.POSITIVE

