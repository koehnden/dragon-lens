from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_brand_columns(connection) -> None:
    inspector = inspect(connection)
    if "brands" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("brands")}
    migrations = [
        (
            "is_user_input",
            "ALTER TABLE brands ADD COLUMN is_user_input BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            "original_name",
            "ALTER TABLE brands ADD COLUMN original_name VARCHAR(255) NOT NULL DEFAULT ''",
        ),
        (
            "translated_name",
            "ALTER TABLE brands ADD COLUMN translated_name VARCHAR(255)",
        ),
        (
            "entity_type",
            "ALTER TABLE brands ADD COLUMN entity_type VARCHAR(50) NOT NULL DEFAULT 'BRAND'",
        ),
    ]
    for name, statement in migrations:
        if name not in columns:
            connection.execute(text(statement))


def init_db() -> None:
    with engine.begin() as connection:
        ensure_brand_columns(connection)

    Base.metadata.create_all(bind=engine)
