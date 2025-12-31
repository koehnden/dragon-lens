import asyncio
import re
from typing import TYPE_CHECKING

from prompts import load_prompt

if TYPE_CHECKING:
    from services.ollama import OllamaService


MAX_ENTITY_TRANSLATION_LENGTH = 50


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
