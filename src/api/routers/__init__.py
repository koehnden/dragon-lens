"""API routers."""

try:
    from api.routers import feedback, metrics, tracking, verticals
except ImportError:
    from src.api.routers import feedback, metrics, tracking, verticals

__all__ = ["feedback", "verticals", "tracking", "metrics"]
