try:
    # When package is installed, api is a top-level module
    from api.app import app
except ImportError:
    # When running from source, api is under src
    from src.api.app import app

__all__ = ["app"]
