from datetime import datetime

import pytest


class DummyTranslator:
    def translate_text_sync(self, text: str, source_lang: str, target_lang: str) -> str:
        return text


def _build_answer(db_session, vertical_id: int, text_zh: str):
    from models import LLMAnswer, Prompt, PromptLanguage, Run, RunStatus

    run = Run(vertical_id=vertical_id, model_name="qwen", status=RunStatus.COMPLETED, run_time=datetime.utcnow())
    db_session.add(run)
    db_session.flush()

    prompt = Prompt(vertical_id=vertical_id, text_zh="test", text_en="test", language_original=PromptLanguage.ZH)
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(run_id=run.id, prompt_id=prompt.id, raw_answer_zh=text_zh, raw_answer_en="")
    db_session.add(answer)
    db_session.flush()
    return answer


def _build_product(db_session, vertical_id: int, name: str):
    from models import Product

    product = Product(vertical_id=vertical_id, brand_id=None, display_name=name, original_name=name, translated_name=None)
    db_session.add(product)
    db_session.flush()
    return product


def test_create_product_mentions_sets_rank_list_position(db_session):
    from models import ProductMention, Vertical
    from workers.tasks import _create_product_mentions

    vertical = Vertical(name="SUV Cars", description="test")
    db_session.add(vertical)
    db_session.flush()

    rav4 = _build_product(db_session, vertical.id, "RAV4")
    crv = _build_product(db_session, vertical.id, "CR-V")
    answer = _build_answer(db_session, vertical.id, "1. CR-V\n2. RAV4")

    _create_product_mentions(db_session, answer, [rav4, crv], answer.raw_answer_zh, DummyTranslator())
    db_session.commit()

    mentions = db_session.query(ProductMention).filter(ProductMention.llm_answer_id == answer.id).all()
    ranks = {m.product.display_name: m.rank for m in mentions}
    assert ranks["CR-V"] == 1
    assert ranks["RAV4"] == 2


def test_create_product_mentions_sets_rank_first_occurrence(db_session):
    from models import ProductMention, Vertical
    from workers.tasks import _create_product_mentions

    vertical = Vertical(name="Sedans", description="test")
    db_session.add(vertical)
    db_session.flush()

    a = _build_product(db_session, vertical.id, "Alpha")
    b = _build_product(db_session, vertical.id, "Beta")
    answer = _build_answer(db_session, vertical.id, "Beta不错，Alpha也可以。")

    _create_product_mentions(db_session, answer, [a, b], answer.raw_answer_zh, DummyTranslator())
    db_session.commit()

    mentions = db_session.query(ProductMention).filter(ProductMention.llm_answer_id == answer.id).all()
    ranks = {m.product.display_name: m.rank for m in mentions}
    assert ranks["Beta"] == 1
    assert ranks["Alpha"] == 2


def test_create_product_mentions_caps_rank_at_10(db_session):
    from models import ProductMention, Vertical
    from workers.tasks import _create_product_mentions

    vertical = Vertical(name="Cap Test", description="test")
    db_session.add(vertical)
    db_session.flush()

    product = _build_product(db_session, vertical.id, "P12")
    text = "\n".join([f"- item{i}" for i in range(1, 12)]) + "\n- P12"
    answer = _build_answer(db_session, vertical.id, text)

    _create_product_mentions(db_session, answer, [product], answer.raw_answer_zh, DummyTranslator())
    db_session.commit()

    mention = db_session.query(ProductMention).filter(ProductMention.llm_answer_id == answer.id).one()
    assert mention.rank == 10


def test_create_product_mentions_skips_unmentioned_products(db_session):
    from models import ProductMention, Vertical
    from workers.tasks import _create_product_mentions

    vertical = Vertical(name="Skip Test", description="test")
    db_session.add(vertical)
    db_session.flush()

    missing = _build_product(db_session, vertical.id, "Missing")
    answer = _build_answer(db_session, vertical.id, "这里没有产品名")

    _create_product_mentions(db_session, answer, [missing], answer.raw_answer_zh, DummyTranslator())
    db_session.commit()

    mentions = db_session.query(ProductMention).filter(ProductMention.llm_answer_id == answer.id).all()
    assert mentions == []
