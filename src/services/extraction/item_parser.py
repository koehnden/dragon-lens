"""Parse response text into extraction items."""

from __future__ import annotations

from services.brand_recognition.list_processor import (
    _get_header_context_text,
    _get_intro_text,
    is_list_format,
    split_into_list_items,
)
from services.extraction.models import ResponseItem


def parse_response_into_items(
    text: str,
    response_id: str | None = None,
) -> list[ResponseItem]:
    """Parse a response into list/table items or a single fallback item."""
    content = (text or "").strip()
    if not content:
        return []

    if is_list_format(content):
        items = split_into_list_items(content)
        if items:
            return [
                ResponseItem(text=item.strip(), position=index, response_id=response_id)
                for index, item in enumerate(items)
                if item.strip()
            ]

    return [ResponseItem(text=content, position=0, response_id=response_id)]


def extract_intro_context(text: str) -> str | None:
    """Return pre-list intro and header context as a compact context block."""
    parts: list[str] = []
    intro = _get_intro_text(text or "")
    if intro:
        parts.append(intro.strip())
    header = _get_header_context_text(text or "")
    if header:
        parts.append(header.strip())
    if not parts:
        return None
    return "\n".join(part for part in parts if part)
