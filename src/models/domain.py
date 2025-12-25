import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


class Vertical(Base):
    __tablename__ = "verticals"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brands: Mapped[List["Brand"]] = relationship("Brand", back_populates="vertical", cascade="all, delete-orphan")
    prompts: Mapped[List["Prompt"]] = relationship("Prompt", back_populates="vertical", cascade="all, delete-orphan")
    runs: Mapped[List["Run"]] = relationship("Run", back_populates="vertical", cascade="all, delete-orphan")


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    translated_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    aliases: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # {"zh": [...], "en": [...]}
    is_user_input: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["Vertical"] = relationship(Vertical, back_populates="brands")
    mentions: Mapped[List["BrandMention"]] = relationship(
        "BrandMention", back_populates="brand", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    brand_id: Mapped[Optional[int]] = mapped_column(ForeignKey("brands.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    translated_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_user_input: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["Vertical"] = relationship(Vertical)
    brand: Mapped[Optional["Brand"]] = relationship(Brand)
    mentions: Mapped[List["ProductMention"]] = relationship(
        "ProductMention", back_populates="product", cascade="all, delete-orphan"
    )


class PromptLanguage(str, enum.Enum):
    EN = "en"
    ZH = "zh"


class LLMProvider(str, enum.Enum):
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    KIMI = "kimi"


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    text_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language_original: Mapped[PromptLanguage] = mapped_column(
        Enum(PromptLanguage), nullable=False, default=PromptLanguage.ZH
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["Vertical"] = relationship(Vertical, back_populates="prompts")
    answers: Mapped[List["LLMAnswer"]] = relationship("LLMAnswer", back_populates="prompt", cascade="all, delete-orphan")


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="qwen")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), nullable=False, default=RunStatus.PENDING)
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    vertical: Mapped["Vertical"] = relationship(Vertical, back_populates="runs")
    answers: Mapped[List["LLMAnswer"]] = relationship("LLMAnswer", back_populates="run", cascade="all, delete-orphan")


class LLMAnswer(Base):
    __tablename__ = "llm_answers"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="qwen")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_answer_zh: Mapped[str] = mapped_column(Text, nullable=False)
    raw_answer_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Response latency in seconds")
    cost_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["Run"] = relationship(Run, back_populates="answers")
    prompt: Mapped["Prompt"] = relationship(Prompt, back_populates="answers")
    mentions: Mapped[List["BrandMention"]] = relationship(
        "BrandMention", back_populates="llm_answer", cascade="all, delete-orphan"
    )
    product_mentions: Mapped[List["ProductMention"]] = relationship(
        "ProductMention", back_populates="llm_answer", cascade="all, delete-orphan"
    )


class Sentiment(str, enum.Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class BrandMention(Base):
    __tablename__ = "brand_mentions"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    llm_answer_id: Mapped[int] = mapped_column(ForeignKey("llm_answers.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    mentioned: Mapped[bool] = mapped_column(nullable=False, default=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Position in listing
    sentiment: Mapped[Sentiment] = mapped_column(Enum(Sentiment), nullable=False, default=Sentiment.NEUTRAL)
    evidence_snippets: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # {"zh": [...], "en": [...]}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    llm_answer: Mapped["LLMAnswer"] = relationship(LLMAnswer, back_populates="mentions")
    brand: Mapped["Brand"] = relationship(Brand, back_populates="mentions")


class ProductMention(Base):
    __tablename__ = "product_mentions"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    llm_answer_id: Mapped[int] = mapped_column(ForeignKey("llm_answers.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    mentioned: Mapped[bool] = mapped_column(nullable=False, default=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sentiment: Mapped[Sentiment] = mapped_column(Enum(Sentiment), nullable=False, default=Sentiment.NEUTRAL)
    evidence_snippets: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    llm_answer: Mapped["LLMAnswer"] = relationship(LLMAnswer, back_populates="product_mentions")
    product: Mapped["Product"] = relationship(Product, back_populates="mentions")


class DailyMetrics(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="qwen")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    mention_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    share_of_voice: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top_spot_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sentiment_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dragon_lens_visibility: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RunMetrics(Base):
    __tablename__ = "run_metrics"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    mention_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    share_of_voice: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top_spot_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sentiment_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dragon_lens_visibility: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
