from typing import Dict, List, Optional


def parse_prompt_entries(raw_prompts: str, language: str) -> List[Dict[str, Optional[str]]]:
    prompts: List[Dict[str, Optional[str]]] = []
    for line in raw_prompts.splitlines():
        text = line.strip()
        if not text:
            continue
        if language == "zh":
            prompts.append({"text_zh": text, "text_en": None, "language_original": "zh"})
        else:
            prompts.append({"text_zh": None, "text_en": text, "language_original": "en"})
    return prompts
