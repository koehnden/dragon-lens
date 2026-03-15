from __future__ import annotations

import json

from prompts import load_prompt


def build_product_comparison_prompt_generation_prompt(pairs: list[dict]) -> str:
    pairs_json = json.dumps(pairs or [], ensure_ascii=False)
    return load_prompt("comparison_prompts/generate_product_comparison_prompts", pairs_json=pairs_json)
