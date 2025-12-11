import sys
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src_path = root / "src"
    if str(src_path) not in sys.path:
        sys.path.append(str(src_path))


ensure_src_on_path()
