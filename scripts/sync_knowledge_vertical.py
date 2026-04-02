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
from services.knowledge_session import knowledge_session  # noqa: E402
from services.knowledge_sync import build_knowledge_sync_request  # noqa: E402


def main() -> None:
    args = parse_args()
    payload = _build_payload(args.vertical, args.submission_id, args.app_version)
    response = _post_payload(
        _knowledge_sync_url(args.url),
        _required_token(
            args.token, settings.knowledge_sync_token or settings.admin_api_token
        ),
        payload.model_dump(mode="json"),
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push a local knowledge vertical snapshot to the hosted admin API"
    )
    parser.add_argument("vertical", help="Canonical knowledge vertical name")
    parser.add_argument("--url", help="Override knowledge sync endpoint URL")
    parser.add_argument("--token", help="Override knowledge sync bearer token")
    parser.add_argument(
        "--submission-id",
        default=f"knowledge-sync-{uuid4().hex}",
        help="Submission identifier for idempotency and auditability",
    )
    parser.add_argument(
        "--app-version",
        default=None,
        help="Optional client version attached to the submission",
    )
    return parser.parse_args()


def _build_payload(vertical: str, submission_id: str, app_version: str | None):
    with knowledge_session() as knowledge_db:
        return build_knowledge_sync_request(
            knowledge_db,
            vertical_name=vertical,
            submission_id=submission_id,
            source_app_version=app_version,
        )


def _knowledge_sync_url(url: str | None) -> str:
    if url:
        return url
    if settings.knowledge_sync_url:
        return settings.knowledge_sync_url
    return f"{settings.resolved_backend_api_base_url}/api/v1/admin/knowledge-sync"


def _required_token(arg_token: str | None, configured_token: str | None) -> str:
    token = arg_token or configured_token
    if token:
        return token
    raise SystemExit(
        "Missing knowledge sync token. Set KNOWLEDGE_SYNC_TOKEN or pass --token."
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
