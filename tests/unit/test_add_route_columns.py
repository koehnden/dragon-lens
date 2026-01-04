import sqlite3
from pathlib import Path

from scripts.add_route_columns import migrate_route_columns


def create_legacy_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, model_name TEXT)")
    cursor.execute("CREATE TABLE llm_answers (id INTEGER PRIMARY KEY, run_id INTEGER)")
    conn.commit()
    conn.close()


def get_column_names(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    names = {row[1] for row in cursor.fetchall()}
    conn.close()
    return names


def test_migrate_route_columns_adds_missing_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    create_legacy_db(db_path)
    updated = migrate_route_columns(db_path)
    assert set(updated) == {"runs", "llm_answers"}
    assert "route" in get_column_names(db_path, "runs")
    assert "route" in get_column_names(db_path, "llm_answers")
