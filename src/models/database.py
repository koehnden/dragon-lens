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


def init_db() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = inspector.get_table_names()

        if "brands" in existing_tables:
            brand_columns = {column["name"] for column in inspector.get_columns("brands")}
            if "is_user_input" not in brand_columns:
                connection.execute(
                    text(
                        "ALTER TABLE brands ADD COLUMN is_user_input BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
            if "original_name" not in brand_columns:
                connection.execute(
                    text(
                        "ALTER TABLE brands ADD COLUMN original_name VARCHAR(255) NOT NULL DEFAULT ''"
                    )
                )
            if "translated_name" not in brand_columns:
                connection.execute(
                    text(
                        "ALTER TABLE brands ADD COLUMN translated_name VARCHAR(255)"
                    )
                )

    Base.metadata.create_all(bind=engine)
