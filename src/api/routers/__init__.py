"""API routers."""

try:
    from api.routers import feedback, knowledge, metrics, tracking, verticals
except ImportError:
    from src.api.routers import feedback, knowledge, metrics, tracking, verticals

__all__ = ["feedback", "knowledge", "verticals", "tracking", "metrics"]
