import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

WIKIDATA_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
WIKIDATA_CACHE_PATH = os.path.join(WIKIDATA_CACHE_DIR, "wikidata_cache.db")

WikidataBase = declarative_base()


class WikidataIndustry(WikidataBase):
    __tablename__ = "wikidata_industries"

    id = Column(Integer, primary_key=True)
    wikidata_id = Column(String(20), unique=True, nullable=False)
    name_en = Column(String(100), nullable=False)
    name_zh = Column(String(100))
    keywords = Column(Text)
    loaded_at = Column(DateTime, default=datetime.utcnow)

    entities = relationship("WikidataEntity", back_populates="industry")
    load_status = relationship("WikidataLoadStatus", back_populates="industry", uselist=False)


class WikidataEntity(WikidataBase):
    __tablename__ = "wikidata_entities"

    id = Column(Integer, primary_key=True)
    wikidata_id = Column(String(20), unique=True, nullable=False)
    entity_type = Column(String(20), nullable=False)
    industry_id = Column(Integer, ForeignKey("wikidata_industries.id"))
    parent_brand_id = Column(Integer, ForeignKey("wikidata_entities.id"), nullable=True)
    name_en = Column(String(200))
    name_zh = Column(String(200))
    aliases_en = Column(Text)
    aliases_zh = Column(Text)
    loaded_at = Column(DateTime, default=datetime.utcnow)

    industry = relationship("WikidataIndustry", back_populates="entities")
    parent_brand = relationship("WikidataEntity", remote_side=[id])


class WikidataLoadStatus(WikidataBase):
    __tablename__ = "wikidata_load_status"

    id = Column(Integer, primary_key=True)
    industry_id = Column(Integer, ForeignKey("wikidata_industries.id"), unique=True)
    status = Column(String(20), default="pending")
    brands_count = Column(Integer, default=0)
    products_count = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    industry = relationship("WikidataIndustry", back_populates="load_status")


_wikidata_engine = None
_WikidataSessionLocal = None


def _ensure_cache_dir():
    os.makedirs(WIKIDATA_CACHE_DIR, exist_ok=True)


def get_wikidata_engine():
    global _wikidata_engine
    if _wikidata_engine is None:
        _ensure_cache_dir()
        _wikidata_engine = create_engine(
            f"sqlite:///{WIKIDATA_CACHE_PATH}",
            connect_args={"check_same_thread": False},
        )
        WikidataBase.metadata.create_all(bind=_wikidata_engine)
    return _wikidata_engine


def get_wikidata_session() -> Session:
    global _WikidataSessionLocal
    if _WikidataSessionLocal is None:
        engine = get_wikidata_engine()
        _WikidataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _WikidataSessionLocal()


def clear_wikidata_cache():
    _ensure_cache_dir()
    if os.path.exists(WIKIDATA_CACHE_PATH):
        os.remove(WIKIDATA_CACHE_PATH)
    global _wikidata_engine, _WikidataSessionLocal
    _wikidata_engine = None
    _WikidataSessionLocal = None


def get_cache_stats() -> dict:
    session = get_wikidata_session()
    try:
        industries_count = session.query(WikidataIndustry).count()
        brands_count = session.query(WikidataEntity).filter(
            WikidataEntity.entity_type == "brand"
        ).count()
        products_count = session.query(WikidataEntity).filter(
            WikidataEntity.entity_type == "product"
        ).count()
        return {
            "industries": industries_count,
            "brands": brands_count,
            "products": products_count,
            "cache_path": WIKIDATA_CACHE_PATH,
            "cache_exists": os.path.exists(WIKIDATA_CACHE_PATH),
        }
    finally:
        session.close()
