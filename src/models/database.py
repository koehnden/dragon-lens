from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings
from models.sqlite_config import apply_sqlite_pragmas, is_sqlite_url, sqlite_connect_args

PRODUCT_BRAND_MAPPING_TABLE_SQL = """
CREATE TABLE product_brand_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id INTEGER NOT NULL REFERENCES verticals(id),
    product_id INTEGER REFERENCES products(id),
    brand_id INTEGER REFERENCES brands(id),
    canonical_product_id INTEGER REFERENCES canonical_products(id),
    canonical_brand_id INTEGER REFERENCES canonical_brands(id),
    confidence FLOAT NOT NULL DEFAULT 0.0,
    is_validated BOOLEAN NOT NULL DEFAULT 0,
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args=sqlite_connect_args(settings.database_url),
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _apply_sqlite_pragmas(dbapi_connection, _):
    apply_sqlite_pragmas(dbapi_connection)


if is_sqlite_url(settings.database_url):
    event.listen(engine, "connect", _apply_sqlite_pragmas)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_brands_table(connection, inspector):
    if "brands" in inspector.get_table_names():
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


def _migrate_runs_table(connection, inspector):
    if "runs" in inspector.get_table_names():
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        if "provider" not in run_columns:
            connection.execute(
                text(
                    "ALTER TABLE runs ADD COLUMN provider VARCHAR(50) NOT NULL DEFAULT 'qwen'"
                )
            )


def _migrate_llm_answers_table(connection, inspector):
    if "llm_answers" in inspector.get_table_names():
        answer_columns = {column["name"] for column in inspector.get_columns("llm_answers")}
        if "provider" not in answer_columns:
            connection.execute(
                text(
                    "ALTER TABLE llm_answers ADD COLUMN provider VARCHAR(50) NOT NULL DEFAULT 'qwen'"
                )
            )
        if "model_name" not in answer_columns:
            connection.execute(
                text(
                    "ALTER TABLE llm_answers ADD COLUMN model_name VARCHAR(255) NOT NULL DEFAULT 'qwen2.5:7b-instruct-q4_0'"
                )
            )
        if "latency" not in answer_columns:
            connection.execute(
                text(
                    "ALTER TABLE llm_answers ADD COLUMN latency FLOAT"
                )
            )


def _migrate_daily_metrics_table(connection, inspector):
    if "daily_metrics" in inspector.get_table_names():
        metrics_columns = {column["name"] for column in inspector.get_columns("daily_metrics")}
        if "provider" not in metrics_columns:
            connection.execute(
                text(
                    "ALTER TABLE daily_metrics ADD COLUMN provider VARCHAR(50) NOT NULL DEFAULT 'qwen'"
                )
            )


def _migrate_prompts_table(connection, inspector):
    if "prompts" in inspector.get_table_names():
        prompt_columns = {col["name"] for col in inspector.get_columns("prompts")}
        if "run_id" not in prompt_columns:
            connection.execute(
                text("ALTER TABLE prompts ADD COLUMN run_id INTEGER REFERENCES runs(id)")
            )


def _migrate_consolidation_debug_table(connection, inspector):
    if "consolidation_debug" in inspector.get_table_names():
        debug_columns = {col["name"] for col in inspector.get_columns("consolidation_debug")}
        if "rejected_at_list_filter_brands" not in debug_columns:
            connection.execute(
                text(
                    "ALTER TABLE consolidation_debug ADD COLUMN rejected_at_list_filter_brands TEXT"
                )
            )
        if "rejected_at_list_filter_products" not in debug_columns:
            connection.execute(
                text(
                    "ALTER TABLE consolidation_debug ADD COLUMN rejected_at_list_filter_products TEXT"
                )
            )


def _migrate_api_keys_table(connection, inspector):
    if "api_keys" not in inspector.get_table_names():
        connection.execute(
            text(
                """
                CREATE TABLE api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL,
                    encrypted_key TEXT NOT NULL,
                    key_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE NOT NULL
                )
                """
            )
        )
        connection.execute(
            text("CREATE INDEX idx_api_keys_provider ON api_keys (provider)")
        )
        connection.execute(
            text("CREATE INDEX idx_api_keys_key_hash ON api_keys (key_hash)")
        )


def _migrate_product_brand_mapping_table(connection, inspector):
    if "product_brand_mappings" in inspector.get_table_names():
        return
    connection.execute(text(PRODUCT_BRAND_MAPPING_TABLE_SQL))


def init_db() -> None:
    if not is_sqlite_url(settings.database_url):
        from models.migrations import upgrade_db

        upgrade_db()
        return
    with engine.begin() as connection:
        inspector = inspect(connection)
        
        _migrate_brands_table(connection, inspector)
        _migrate_runs_table(connection, inspector)
        _migrate_llm_answers_table(connection, inspector)
        _migrate_daily_metrics_table(connection, inspector)
        _migrate_prompts_table(connection, inspector)
        _migrate_consolidation_debug_table(connection, inspector)
        _migrate_api_keys_table(connection, inspector)
        _migrate_product_brand_mapping_table(connection, inspector)

    Base.metadata.create_all(bind=engine)
