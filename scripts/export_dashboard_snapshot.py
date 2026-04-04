import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config import settings  # noqa: E402
from models.database import SessionLocal, init_db  # noqa: E402
from services.demo_dashboard_snapshot import build_dashboard_snapshot  # noqa: E402


def main() -> None:
    args = parse_args()
    init_db()
    with SessionLocal() as db:
        snapshot = build_dashboard_snapshot(
            db,
            vertical_ids=args.vertical_ids,
            vertical_names=args.vertical_names,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        snapshot.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(f"Wrote dashboard snapshot to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a dashboard snapshot for the Streamlit Community Cloud demo"
    )
    selector = parser.add_mutually_exclusive_group(required=False)
    selector.add_argument(
        "--vertical-id",
        dest="vertical_ids",
        action="append",
        type=int,
        help="Include a vertical by ID. Repeat to include multiple verticals.",
    )
    selector.add_argument(
        "--vertical-name",
        dest="vertical_names",
        action="append",
        help="Include a vertical by name. Repeat to include multiple verticals.",
    )
    parser.add_argument(
        "--output",
        default=settings.dashboard_snapshot_path,
        help="Output path for the snapshot JSON",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
