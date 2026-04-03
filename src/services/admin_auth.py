from hmac import compare_digest

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

security = HTTPBearer(auto_error=False)


def require_knowledge_sync_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> None:
    _require_token(credentials, settings.knowledge_sync_token or settings.admin_api_token)


def require_demo_publish_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> None:
    _require_token(credentials, settings.demo_publish_token or settings.admin_api_token)


def _require_token(
    credentials: HTTPAuthorizationCredentials | None,
    expected_token: str | None,
) -> None:
    if not expected_token:
        raise HTTPException(status_code=503, detail="Admin token not configured")
    if credentials is None or not compare_digest(credentials.credentials, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
