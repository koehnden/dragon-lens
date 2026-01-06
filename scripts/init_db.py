import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import init_db
from src.models.knowledge_database import init_knowledge_db

if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    init_knowledge_db()
    print("✅ Database tables created successfully!")
