import sqlite3
import sys
from pathlib import Path


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def add_column(cursor: sqlite3.Cursor, table: str, column: str, column_type: str) -> None:
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def ensure_route_column(cursor: sqlite3.Cursor, table: str) -> bool:
    if column_exists(cursor, table, "route"):
        return False
    add_column(cursor, table, "route", "VARCHAR(20)")
    return True


def update_route_columns(connection: sqlite3.Connection) -> list[str]:
    cursor = connection.cursor()
    updated_tables = []
    for table in ("runs", "llm_answers"):
        if ensure_route_column(cursor, table):
            updated_tables.append(table)
    if updated_tables:
        connection.commit()
    return updated_tables


def migrate_route_columns(db_path: Path) -> list[str]:
    connection = sqlite3.connect(str(db_path))
    updated_tables = update_route_columns(connection)
    connection.close()
    return updated_tables


def get_db_path(args: list[str]) -> Path:
    if args:
        return Path(args[0]).expanduser()
    return Path(__file__).resolve().parents[1] / "dragonlens.db"


def main() -> None:
    db_path = get_db_path(sys.argv[1:])
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)
    updated_tables = migrate_route_columns(db_path)
    if updated_tables:
        print(f"Added route column to: {', '.join(updated_tables)}")
        return
    print("Route columns already present")


if __name__ == "__main__":
    main()
