import asyncio
import json
import re
from typing import TYPE_CHECKING

from prompts import load_prompt

if TYPE_CHECKING:
    from services.ollama import OllamaService


MAX_ENTITY_TRANSLATION_LENGTH = 50
MAX_ENTITY_ENGLISH_NAME_LENGTH = 30


def has_latin_letters(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def has_chinese_characters(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def extract_english_part(text: str) -> str:
    if not text:
        return ""
    english_chars = re.findall(r"[A-Za-z0-9\-\.]+", text)
    return " ".join(english_chars).strip()


def extract_chinese_part(text: str) -> str:
    if not text:
        return ""
    chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    return "".join(chinese_chars).strip()


def capitalize_brand_name(name: str) -> str:
    if not name:
        return name
    if name.isupper() and len(name) <= 4:
        return name
    if re.match(r"^[A-Z][a-z]+(-[A-Z][a-z]+)*$", name):
        return name
    if re.match(r"^[A-Z][a-z]+\s+[A-Z]", name):
        return name
    if has_chinese_characters(name):
        return name
    if "-" in name:
        parts = name.split("-")
        return "-".join(capitalize_brand_name(p) for p in parts)
    words = name.split()
    capitalized = []
    for word in words:
        if word.isupper() and len(word) <= 4:
            capitalized.append(word)
        elif re.match(r"^[A-Z][a-z]+$", word):
            capitalized.append(word)
        else:
            capitalized.append(word.capitalize())
    return " ".join(capitalized)


def format_entity_label(original: str, translated: str | None) -> str:
    base = (original or "").strip()
    alt = (translated or "").strip()
    english_name = _find_english_name(base, alt)
    chinese_name = _find_chinese_name(base, alt)
    english_formatted = capitalize_brand_name(english_name) if english_name else ""
    if english_formatted and chinese_name:
        return f"{english_formatted} ({chinese_name})"
    if english_formatted:
        return english_formatted
    return base


def _find_english_name(original: str, translated: str) -> str:
    for text in [original, translated]:
        if not text:
            continue
        if has_latin_letters(text) and not has_chinese_characters(text):
            return text
    for text in [original, translated]:
        if text and has_latin_letters(text) and has_chinese_characters(text):
            return extract_english_part(text)
    return ""


def _find_chinese_name(original: str, translated: str) -> str:
    for text in [original, translated]:
        if not text:
            continue
        if has_chinese_characters(text) and not has_latin_letters(text):
            return text
    for text in [original, translated]:
        if text and has_chinese_characters(text) and has_latin_letters(text):
            return extract_chinese_part(text)
    return ""


def _clean_entity_translation(text: str, original: str) -> str:
    if not text:
        return original
    cleaned = re.sub(r"\s*\([Nn]ote:.*\)$", "", text)
    cleaned = re.sub(r"\s*\([Tt]his\s+(is|means).*\)$", "", cleaned)
    cleaned = re.sub(r"\s*\(.*translation.*\)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(.*misspelling.*\)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if len(cleaned) > MAX_ENTITY_TRANSLATION_LENGTH:
        return original
    if not cleaned:
        return original
    return cleaned


class TranslaterService:
    def __init__(self, ollama_service: "OllamaService | None" = None):
        if ollama_service is None:
            from services.ollama import OllamaService
            ollama_service = OllamaService()
        self.ollama = ollama_service

    async def translate_entities_to_english_batch(
        self,
        items: list[dict],
        vertical_name: str,
        vertical_description: str | None,
    ) -> dict[tuple[str, str], str]:
        results = await _translate_entity_batch(self.ollama, items, vertical_name, vertical_description, retry=False)
        missing = [i for i in items if (i["type"], i["name"]) not in results]
        if not missing:
            return results
        retry_results = await _translate_entity_batch(self.ollama, missing, vertical_name, vertical_description, retry=True)
        return {**results, **retry_results}

    async def translate_entity(self, name: str) -> str:
        if has_latin_letters(name):
            return name
        prompt = _build_entity_prompt(name)
        system_prompt = _entity_system_prompt()
        return await _translate_with_guardrails(
            self.ollama, name, prompt, system_prompt, is_entity=True
        )

    def translate_entity_sync(self, name: str) -> str:
        return asyncio.run(self.translate_entity(name))

    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        prompt = _build_text_prompt(text, source_lang, target_lang)
        system_prompt = _text_system_prompt(source_lang, target_lang)
        return await _translate_with_guardrails(self.ollama, text, prompt, system_prompt)

    def translate_text_sync(self, text: str, source_lang: str, target_lang: str) -> str:
        return asyncio.run(self.translate_text(text, source_lang, target_lang))

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        max_batch_size: int = 20,
    ) -> list[str]:
        if not texts:
            return []
        if len(texts) == 1:
            result = await self.translate_text(texts[0], source_lang, target_lang)
            return [result]
        non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty_indices:
            return [""] * len(texts)
        non_empty_texts = [texts[i] for i in non_empty_indices]
        translated = await _translate_batch_internal(
            self.ollama, non_empty_texts, source_lang, target_lang, max_batch_size
        )
        results = [""] * len(texts)
        for idx, trans in zip(non_empty_indices, translated):
            results[idx] = trans
        return results

    def translate_batch_sync(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        max_batch_size: int = 20,
    ) -> list[str]:
        return asyncio.run(self.translate_batch(texts, source_lang, target_lang, max_batch_size))


def _build_entity_prompt(name: str) -> str:
    return load_prompt("translation/entity_translation_user_prompt", name=name)


def _entity_system_prompt() -> str:
    return load_prompt("translation/entity_translation_system_prompt")


def _build_text_prompt(text: str, source_lang: str, target_lang: str) -> str:
    return load_prompt(
        "translation/text_translation_user_prompt",
        text=text,
        source_lang=source_lang,
        target_lang=target_lang,
    )


def _text_system_prompt(source_lang: str, target_lang: str) -> str:
    return load_prompt(
        "translation/text_translation_system_prompt",
        source_lang=source_lang,
        target_lang=target_lang,
    )


async def _translate_with_guardrails(
    service: "OllamaService",
    fallback: str,
    prompt: str,
    system_prompt: str,
    is_entity: bool = False,
) -> str:
    try:
        response = await service._call_ollama(
            model=service.translation_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )
    except Exception:
        return fallback
    cleaned = (response or "").strip()
    if is_entity:
        cleaned = _clean_entity_translation(cleaned, fallback)
    return cleaned or fallback


def _is_valid_english_entity_name(name: str | None) -> bool:
    if not name:
        return False
    cleaned = name.strip()
    if not cleaned or len(cleaned) > MAX_ENTITY_ENGLISH_NAME_LENGTH:
        return False
    if has_chinese_characters(cleaned):
        return False
    if any(c in cleaned for c in ["(", ")", "\n", "\r", ":", "："]):
        return False
    return True


def _json_array_from_text(text: str) -> list[dict] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return None


async def _translate_entity_batch(
    service: "OllamaService",
    items: list[dict],
    vertical_name: str,
    vertical_description: str | None,
    retry: bool,
) -> dict[tuple[str, str], str]:
    items_json = json.dumps(items, ensure_ascii=False)
    sys_id = "translation/entity_name_en_batch_retry_system_prompt" if retry else "translation/entity_name_en_batch_system_prompt"
    user_id = "translation/entity_name_en_batch_retry_user_prompt" if retry else "translation/entity_name_en_batch_user_prompt"
    prompt = load_prompt(user_id, vertical_name=vertical_name, vertical_description=vertical_description or "", items_json=items_json)
    system_prompt = load_prompt(sys_id)
    try:
        response = await service._call_ollama(model=service.translation_model, prompt=prompt, system_prompt=system_prompt, temperature=0.1)
    except Exception:
        return {}
    parsed = _json_array_from_text(response)
    if not parsed:
        return {}
    out: dict[tuple[str, str], str] = {}
    for item in parsed:
        t = (item.get("type") or "").strip()
        name = (item.get("name") or "").strip()
        english = item.get("english")
        if not t or not name or not _is_valid_english_entity_name(english):
            continue
        out[(t, name)] = str(english).strip()
    return out


async def _translate_batch_internal(
    service: "OllamaService",
    texts: list[str],
    source_lang: str,
    target_lang: str,
    max_batch_size: int,
) -> list[str]:
    if len(texts) <= max_batch_size:
        return await _translate_single_batch(service, texts, source_lang, target_lang)
    results: list[str] = []
    for i in range(0, len(texts), max_batch_size):
        batch = texts[i : i + max_batch_size]
        batch_results = await _translate_single_batch(service, batch, source_lang, target_lang)
        results.extend(batch_results)
    return results


async def _translate_single_batch(
    service: "OllamaService",
    texts: list[str],
    source_lang: str,
    target_lang: str,
) -> list[str]:
    texts_json = json.dumps(texts, ensure_ascii=False)
    system_prompt = load_prompt(
        "translation/batch_translation_system_prompt",
        source_lang=source_lang,
        target_lang=target_lang,
    )
    prompt = load_prompt("translation/batch_translation_user_prompt", texts_json=texts_json)
    try:
        response = await service._call_ollama(
            model=service.translation_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )
    except Exception:
        return list(texts)
    return _parse_batch_translation_response(response, texts)


def _parse_batch_translation_response(response: str, original_texts: list[str]) -> list[str]:
    raw = (response or "").strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return list(original_texts)
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return list(original_texts)
    if not isinstance(parsed, list):
        return list(original_texts)
    if len(parsed) != len(original_texts):
        return list(original_texts)
    results = []
    for i, item in enumerate(parsed):
        if isinstance(item, str) and item.strip():
            results.append(item.strip())
        else:
            results.append(original_texts[i])
    return results
