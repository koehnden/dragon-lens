import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models.knowledge_database import init_knowledge_db


def main() -> int:
    init_knowledge_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
