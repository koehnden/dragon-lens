import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config import settings  # noqa: E402
from models import Vertical  # noqa: E402
from models.database import SessionLocal, init_db  # noqa: E402
from services.demo_publish import build_demo_publish_request  # noqa: E402


def main() -> None:
    args = parse_args()
    init_db()
    with SessionLocal() as db:
        vertical_id = _vertical_id(db, args.vertical_id, args.vertical_name)
        payload = build_demo_publish_request(
            db,
            vertical_id=vertical_id,
            submission_id=args.submission_id,
            source_app_version=args.app_version,
        )
    response = _post_payload(
        _publish_url(args.url),
        _required_token(
            args.token, settings.demo_publish_token or settings.admin_api_token
        ),
        payload.model_dump(mode="json"),
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a local vertical snapshot to the hosted demo admin API"
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--vertical-id", type=int, help="Local vertical ID")
    selector.add_argument("--vertical-name", help="Local vertical name")
    parser.add_argument("--url", help="Override demo publish endpoint URL")
    parser.add_argument("--token", help="Override demo publish bearer token")
    parser.add_argument(
        "--submission-id",
        default=f"demo-publish-{uuid4().hex}",
        help="Submission identifier for this publish action",
    )
    parser.add_argument(
        "--app-version",
        default=None,
        help="Optional client version attached to the publish action",
    )
    return parser.parse_args()


def _vertical_id(db, vertical_id: int | None, vertical_name: str | None) -> int:
    if vertical_id is not None:
        return vertical_id
    vertical = db.query(Vertical).filter(Vertical.name == vertical_name).first()
    if vertical:
        return vertical.id
    raise SystemExit(f"Vertical not found: {vertical_name}")


def _publish_url(url: str | None) -> str:
    if url:
        return url
    if settings.demo_publish_url:
        return settings.demo_publish_url
    return f"{settings.resolved_backend_api_base_url}/api/v1/admin/demo-publish"


def _required_token(arg_token: str | None, configured_token: str | None) -> str:
    token = arg_token or configured_token
    if token:
        return token
    raise SystemExit(
        "Missing demo publish token. Set DEMO_PUBLISH_TOKEN or pass --token."
    )


def _post_payload(url: str, token: str, payload: dict) -> dict:
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    main()
