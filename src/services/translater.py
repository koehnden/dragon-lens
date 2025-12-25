import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.ollama import OllamaService


def has_latin_letters(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def has_chinese_characters(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


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
    base = original.strip()
    alt = (translated or "").strip()
    base_capitalized = capitalize_brand_name(base)
    alt_capitalized = capitalize_brand_name(alt)
    if not alt_capitalized or alt_capitalized.lower() == base_capitalized.lower():
        return base_capitalized
    has_chinese_in_original = has_chinese_characters(base)
    has_chinese_in_translated = has_chinese_characters(alt)
    if has_chinese_in_original and not has_chinese_in_translated:
        return f"{alt_capitalized} ({base})"
    if has_chinese_in_translated and not has_chinese_in_original:
        return f"{base_capitalized} ({alt})"
    return f"{alt_capitalized} ({base})"


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
        return await _translate_with_guardrails(self.ollama, name, prompt, system_prompt)

    def translate_entity_sync(self, name: str) -> str:
        return asyncio.run(self.translate_entity(name))

    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        prompt = _build_text_prompt(text, source_lang, target_lang)
        system_prompt = _text_system_prompt(source_lang, target_lang)
        return await _translate_with_guardrails(self.ollama, text, prompt, system_prompt)

    def translate_text_sync(self, text: str, source_lang: str, target_lang: str) -> str:
        return asyncio.run(self.translate_text(text, source_lang, target_lang))


def _build_entity_prompt(name: str) -> str:
    prefix = "Translate this brand or product name to English and preserve the entity exactly:"
    return f"{prefix}\n{name}"


def _entity_system_prompt() -> str:
    return (
        "You are a precise translator for brand and product names."
        " Translate to English without inventing or altering names."
        " If you cannot translate confidently, return the original text unchanged."
        " Respond with only the translated name."
    )


def _build_text_prompt(text: str, source_lang: str, target_lang: str) -> str:
    return f"Translate from {source_lang} to {target_lang}:\n{text}"


def _text_system_prompt(source_lang: str, target_lang: str) -> str:
    return (
        f"You are a careful translator. Convert {source_lang} text to {target_lang} without adding, "
        "removing, or fabricating content. Respond only with the translated text."
    )


async def _translate_with_guardrails(
    service: "OllamaService",
    fallback: str,
    prompt: str,
    system_prompt: str,
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
    return cleaned or fallback
