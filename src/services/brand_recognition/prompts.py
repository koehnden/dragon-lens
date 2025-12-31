from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment


def load_prompt(prompt_id: str, **kwargs: Any) -> str:
    template, requires = _load_template(prompt_id)
    _validate_requires(requires, kwargs)
    return _render(template, kwargs)


@lru_cache(maxsize=64)
def _load_template(prompt_id: str) -> tuple[str, list[str]]:
    content = _read_prompt_file(_prompt_path(prompt_id))
    meta, body = _split_frontmatter(content)
    requires = list(meta.get("requires") or [])
    return body, requires


def _prompt_path(prompt_id: str) -> Path:
    base = Path(__file__).resolve().parents[2] / "prompts" / "brand_recognition"
    return base / f"{prompt_id}.md"


def _read_prompt_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _split_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def _render(template: str, context: dict) -> str:
    env = Environment(loader=BaseLoader())
    return env.from_string(template).render(**context)


def _validate_requires(requires: list[str], context: dict) -> None:
    missing = [r for r in requires if r not in context]
    if missing:
        raise ValueError(f"Missing required vars for prompt: {missing}")

