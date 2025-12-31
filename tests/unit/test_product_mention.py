import pytest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, Brand, LLMAnswer, Product, Prompt, Run, Vertical
from models.domain import (
    ProductMention,
    PromptLanguage,
    RunStatus,
    Sentiment,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_vertical(db_session: Session) -> Vertical:
    vertical = Vertical(name="SUV Cars", description="Sport Utility Vehicles")
    db_session.add(vertical)
    db_session.commit()
    return vertical


@pytest.fixture
def sample_brand(db_session: Session, sample_vertical: Vertical) -> Brand:
    brand = Brand(
        vertical_id=sample_vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        aliases={"zh": ["丰田"], "en": []},
    )
    db_session.add(brand)
    db_session.commit()
    return brand


@pytest.fixture
def sample_product(
    db_session: Session, sample_vertical: Vertical, sample_brand: Brand
) -> Product:
    product = Product(
        vertical_id=sample_vertical.id,
        brand_id=sample_brand.id,
        display_name="RAV4",
        original_name="RAV4",
    )
    db_session.add(product)
    db_session.commit()
    return product


@pytest.fixture
def sample_run(db_session: Session, sample_vertical: Vertical) -> Run:
    run = Run(
        vertical_id=sample_vertical.id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def sample_prompt(db_session: Session, sample_vertical: Vertical) -> Prompt:
    prompt = Prompt(
        vertical_id=sample_vertical.id,
        text_zh="推荐一款SUV",
        text_en="Recommend an SUV",
        language_original=PromptLanguage.ZH,
    )
    db_session.add(prompt)
    db_session.commit()
    return prompt


@pytest.fixture
def sample_answer(
    db_session: Session, sample_run: Run, sample_prompt: Prompt
) -> LLMAnswer:
    answer = LLMAnswer(
        run_id=sample_run.id,
        prompt_id=sample_prompt.id,
        model_name="qwen",
        raw_answer_zh="我推荐丰田RAV4",
        raw_answer_en="I recommend Toyota RAV4",
    )
    db_session.add(answer)
    db_session.commit()
    return answer


def test_product_mention_creation(
    db_session: Session, sample_answer: LLMAnswer, sample_product: Product
):
    mention = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=sample_product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["丰田RAV4"], "en": ["Toyota RAV4"]},
    )
    db_session.add(mention)
    db_session.commit()

    retrieved = db_session.query(ProductMention).first()
    assert retrieved is not None
    assert retrieved.mentioned is True
    assert retrieved.rank == 1
    assert retrieved.sentiment == Sentiment.POSITIVE


def test_product_mention_relationship_to_product(
    db_session: Session, sample_answer: LLMAnswer, sample_product: Product
):
    mention = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=sample_product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={},
    )
    db_session.add(mention)
    db_session.commit()

    retrieved = db_session.query(ProductMention).first()
    assert retrieved.product.display_name == "RAV4"
    assert retrieved.product.brand.display_name == "Toyota"


def test_product_mention_relationship_to_answer(
    db_session: Session, sample_answer: LLMAnswer, sample_product: Product
):
    mention = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=sample_product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    db_session.add(mention)
    db_session.commit()

    retrieved = db_session.query(ProductMention).first()
    assert retrieved.llm_answer.raw_answer_zh == "我推荐丰田RAV4"


def test_multiple_product_mentions_per_answer(
    db_session: Session,
    sample_answer: LLMAnswer,
    sample_product: Product,
    sample_vertical: Vertical,
    sample_brand: Brand,
):
    product2 = Product(
        vertical_id=sample_vertical.id,
        brand_id=sample_brand.id,
        display_name="Camry",
        original_name="Camry",
    )
    db_session.add(product2)
    db_session.commit()

    mention1 = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=sample_product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={},
    )
    mention2 = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=product2.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    db_session.add_all([mention1, mention2])
    db_session.commit()

    mentions = db_session.query(ProductMention).all()
    assert len(mentions) == 2
    assert {m.product.display_name for m in mentions} == {"RAV4", "Camry"}


def test_product_mention_null_rank(
    db_session: Session, sample_answer: LLMAnswer, sample_product: Product
):
    mention = ProductMention(
        llm_answer_id=sample_answer.id,
        product_id=sample_product.id,
        mentioned=True,
        rank=None,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={},
    )
    db_session.add(mention)
    db_session.commit()

    retrieved = db_session.query(ProductMention).first()
    assert retrieved.rank is None
