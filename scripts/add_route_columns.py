from pathlib import Path
import sqlite3
import sys


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column(cursor: sqlite3.Cursor, table: str, column: str, column_type: str) -> None:
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _ensure_route_column(cursor: sqlite3.Cursor, table: str) -> bool:
    if _column_exists(cursor, table, "route"):
        return False
    _add_column(cursor, table, "route", "VARCHAR(20)")
    return True


def main() -> None:
    db_path = Path(__file__).resolve().parents[1] / "dragonlens.db"
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        updated_tables = []
        for table in ("runs", "llm_answers"):
            if _ensure_route_column(cursor, table):
                updated_tables.append(table)
        if updated_tables:
            conn.commit()
            print(f"Added route column to: {', '.join(updated_tables)}")
        else:
            print("Route columns already present")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
