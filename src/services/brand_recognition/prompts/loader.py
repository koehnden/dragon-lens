"""Prompt loader for loading and rendering prompt templates."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, BaseLoader

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent


class PromptTemplate:
    def __init__(self, prompt_id: str, content: str, metadata: Dict[str, Any]):
        self.id = prompt_id
        self.content = content
        self.version = metadata.get("version", "v1")
        self.description = metadata.get("description", "")
        self.requires = metadata.get("requires", [])

    def render(self, **kwargs) -> str:
        env = Environment(loader=BaseLoader())
        template = env.from_string(self.content)
        return template.render(**kwargs)


def get_prompt_path(prompt_id: str) -> Path:
    return PROMPTS_DIR / f"{prompt_id}.md"


@lru_cache(maxsize=32)
def _load_prompt_file(prompt_id: str) -> PromptTemplate:
    path = get_prompt_path(prompt_id)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata, template_content = _parse_frontmatter(content)
    return PromptTemplate(prompt_id, template_content, metadata)


def _parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        logger.warning("Failed to parse YAML frontmatter")
        metadata = {}

    template_content = parts[2].strip()
    return metadata, template_content


def load_prompt(prompt_id: str, **kwargs) -> str:
    template = _load_prompt_file(prompt_id)
    missing = [r for r in template.requires if r not in kwargs and kwargs.get(r) is None]
    if missing:
        logger.debug(f"Prompt '{prompt_id}' missing optional vars: {missing}")
    return template.render(**kwargs)


def reload_prompts() -> None:
    _load_prompt_file.cache_clear()
