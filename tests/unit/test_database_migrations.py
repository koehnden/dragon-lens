from sqlalchemy import create_engine, inspect, text

from models.database import ensure_brand_columns


def create_brands_table(connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE brands ("
            "id INTEGER PRIMARY KEY, "
            "vertical_id INTEGER NOT NULL, "
            "display_name VARCHAR(255) NOT NULL, "
            "original_name VARCHAR(255) NOT NULL)"
        )
    )


def test_ensure_brand_columns_adds_entity_type():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        create_brands_table(connection)
        ensure_brand_columns(connection)
        columns = {column["name"] for column in inspect(connection).get_columns("brands")}
    engine.dispose()
    assert "entity_type" in columns
