"""
Async utilities for brand recognition.

This module contains async helper functions and event loop management
for running async code from synchronous contexts.
"""

import asyncio
from typing import Any


_persistent_event_loop = None


def _get_or_create_event_loop():
    """Get or create a persistent event loop."""
    global _persistent_event_loop
    if _persistent_event_loop is None or _persistent_event_loop.is_closed():
        _persistent_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_persistent_event_loop)
    return _persistent_event_loop


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        asyncio.get_running_loop()
        raise RuntimeError("Cannot run async code from within async context. Use await instead.")
    except RuntimeError:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(coro)
