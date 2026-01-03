from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical
from models.domain import BrandAlias, CanonicalBrand, RunStatus, Sentiment
from services.entity_consolidation import consolidate_run


def test_consolidate_run_uses_qwen_normalization(db_session: Session):
    vertical = Vertical(name="Qwen Grouping")
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
        text_zh="测试提示",
        language_original="zh",
    )
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider="qwen",
        model_name="qwen2.5:7b",
        raw_answer_zh="VW 和 Volkswagen",
    )
    db_session.add(answer)
    db_session.flush()

    user_brand = Brand(
        vertical_id=vertical.id,
        display_name="VW",
        original_name="VW",
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )
    discovered_brand = Brand(
        vertical_id=vertical.id,
        display_name="Volkswagen",
        original_name="Volkswagen",
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db_session.add_all([user_brand, discovered_brand])
    db_session.flush()

    mention1 = BrandMention(
        llm_answer_id=answer.id,
        brand_id=user_brand.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
    )
    mention2 = BrandMention(
        llm_answer_id=answer.id,
        brand_id=discovered_brand.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.POSITIVE,
    )
    db_session.add_all([mention1, mention2])
    db_session.flush()

    normalized_brands = {"VW": "Volkswagen", "Volkswagen": "Volkswagen"}

    consolidate_run(db_session, run.id, normalized_brands=normalized_brands)

    canonical = db_session.query(CanonicalBrand).filter(
        CanonicalBrand.canonical_name == "VW"
    ).first()
    assert canonical is not None

    alias = db_session.query(BrandAlias).filter(
        BrandAlias.canonical_brand_id == canonical.id
    ).first()
    assert alias is not None
    assert alias.alias == "Volkswagen"
