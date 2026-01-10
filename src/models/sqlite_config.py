def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite://")


def sqlite_connect_args(url: str) -> dict:
    if not is_sqlite_url(url):
        return {}
    return {"check_same_thread": False, "timeout": 30}


def apply_sqlite_pragmas(connection) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
