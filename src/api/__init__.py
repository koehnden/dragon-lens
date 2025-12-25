try:
    from api.app import app
except ImportError:
    from src.api.app import app

__all__ = ["app"]
