from config import settings


def api_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{settings.resolved_backend_api_base_url}{normalized}"


def is_public_demo() -> bool:
    return settings.is_public_demo
