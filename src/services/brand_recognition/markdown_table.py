"""
Markdown table detection and parsing.

We use a lightweight regex gate to detect likely Markdown tables, and (when
available) Python-Markdown + BeautifulSoup4 to parse them into rows/cells.
"""

from __future__ import annotations

import re
from typing import List, Optional


_TABLE_HEADER_AND_SEPARATOR_RE = re.compile(
    r"(?m)^\s*\|?.*\|.*\|?\s*\n^\s*\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)+\|?\s*$"
)

_TABLE_ROW_RE = re.compile(r"(?m)^\s*\|?.*\|.*\|?\s*$")


def _extract_markdown_table_blocks(text: str) -> List[str]:
    """Extract contiguous Markdown table blocks (header+separator+data rows)."""
    if not text:
        return []

    blocks: List[str] = []
    search_from = 0
    while True:
        match = _TABLE_HEADER_AND_SEPARATOR_RE.search(text, search_from)
        if not match:
            break

        start = match.start()
        end = match.end()

        cursor = end
        while cursor < len(text) and text[cursor] in "\r\n":
            cursor += 1
        # Consume subsequent data rows; allow leading blank lines between tables/sections.
        while cursor < len(text):
            next_newline = text.find("\n", cursor)
            if next_newline == -1:
                line = text[cursor:]
                cursor = len(text)
            else:
                line = text[cursor:next_newline]
                cursor = next_newline + 1

            if not line.strip():
                break
            if line.count("|") < 2:
                break
            if not _TABLE_ROW_RE.match(line):
                break

        block = text[start:cursor].strip()
        if block:
            blocks.append(block)

        search_from = cursor

    return blocks


def find_first_markdown_table_index(text: str) -> Optional[int]:
    """Return the start index of the first Markdown table, if any."""
    if not text:
        return None
    match = _TABLE_HEADER_AND_SEPARATOR_RE.search(text)
    return match.start() if match else None


def markdown_table_has_min_data_rows(text: str, min_rows: int = 2) -> bool:
    """Cheap heuristic: header+separator plus at least `min_rows` pipe rows."""
    if not text:
        return False

    for match in _TABLE_HEADER_AND_SEPARATOR_RE.finditer(text):
        after = text[match.end() :]
        data_rows = 0
        started = False
        for line in after.splitlines():
            if not line.strip():
                if started:
                    break
                continue
            started = True
            if line.count("|") >= 2:
                data_rows += 1
                if data_rows >= min_rows:
                    return True
            else:
                break

    return False


def extract_markdown_table_rows(text: str) -> List[List[str]]:
    """Parse Markdown tables into rows of cell-text (data rows only)."""
    if not markdown_table_has_min_data_rows(text, min_rows=1):
        return []

    try:
        import markdown  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return []

    rows: List[List[str]] = []
    for block in _extract_markdown_table_blocks(text):
        html = markdown.markdown(block, extensions=["tables"])
        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                row = [td.get_text(" ", strip=True) for td in tds]
                row = [cell for cell in row if cell]
                if row:
                    rows.append(row)

    return rows


def extract_markdown_table_row_items(text: str) -> List[str]:
    """Convert each data row into a single 'list item' string."""
    items: List[str] = []
    for row in extract_markdown_table_rows(text):
        item = " | ".join(row).strip()
        if item:
            items.append(item)
    return items
