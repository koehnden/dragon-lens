"""API routers."""

try:
    from api.routers import metrics, tracking, verticals
except ImportError:
    from src.api.routers import metrics, tracking, verticals

__all__ = ["verticals", "tracking", "metrics"]
