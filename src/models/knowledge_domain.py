import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.domain import EntityType
from models.knowledge_database import KnowledgeBase


class KnowledgeVertical(KnowledgeBase):
    __tablename__ = "knowledge_verticals"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeVerticalAlias(KnowledgeBase):
    __tablename__ = "knowledge_vertical_aliases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)


class KnowledgeBrand(KnowledgeBase):
    __tablename__ = "knowledge_brands"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)
    aliases: Mapped[List["KnowledgeBrandAlias"]] = relationship(
        "KnowledgeBrandAlias", back_populates="brand", cascade="all, delete-orphan"
    )


class KnowledgeBrandAlias(KnowledgeBase):
    __tablename__ = "knowledge_brand_aliases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("knowledge_brands.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brand: Mapped["KnowledgeBrand"] = relationship(KnowledgeBrand, back_populates="aliases")


class KnowledgeProduct(KnowledgeBase):
    __tablename__ = "knowledge_products"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    brand_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_brands.id"), nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)
    brand: Mapped[Optional["KnowledgeBrand"]] = relationship(KnowledgeBrand)
    aliases: Mapped[List["KnowledgeProductAlias"]] = relationship(
        "KnowledgeProductAlias", back_populates="product", cascade="all, delete-orphan"
    )


class KnowledgeProductAlias(KnowledgeBase):
    __tablename__ = "knowledge_product_aliases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("knowledge_products.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped["KnowledgeProduct"] = relationship(KnowledgeProduct, back_populates="aliases")


class KnowledgeRejectedEntity(KnowledgeBase):
    __tablename__ = "knowledge_rejected_entities"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)


class KnowledgeProductBrandMapping(KnowledgeBase):
    __tablename__ = "knowledge_product_brand_mappings"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("knowledge_products.id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("knowledge_brands.id"), nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)
    product: Mapped["KnowledgeProduct"] = relationship(KnowledgeProduct)
    brand: Mapped["KnowledgeBrand"] = relationship(KnowledgeBrand)


class KnowledgeTranslationOverride(KnowledgeBase):
    __tablename__ = "knowledge_translation_overrides"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    override_text: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)


class FeedbackStatus(str, enum.Enum):
    RECEIVED = "received"


class KnowledgeFeedbackEvent(KnowledgeBase):
    __tablename__ = "knowledge_feedback_events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("knowledge_verticals.id"), nullable=False)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[FeedbackStatus] = mapped_column(Enum(FeedbackStatus), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vertical: Mapped["KnowledgeVertical"] = relationship(KnowledgeVertical)
