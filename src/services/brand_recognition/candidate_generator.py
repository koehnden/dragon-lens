"""
Candidate generation for entity extraction.

This module generates initial entity candidates from text using multiple
approaches: regex patterns, NLP libraries, alias matching, and seed entities.
"""

import re
import importlib
from typing import Dict, List, Set

from src.constants import (
    KNOWN_PRODUCTS,
    GENERIC_TERMS,
    PRODUCT_HINTS,
)

from services.brand_recognition.models import EntityCandidate


def generate_candidates(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> List[EntityCandidate]:
    """Generate entity candidates from text using multiple approaches."""
    seeds = _seed_primary(primary_brand, aliases)
    alias_hits = _alias_hits(text, _default_alias_table())
    hanlp_entities = _extract_with_hanlp(text)
    ltp_entities = _extract_with_ltp(text)
    regex_hits = _regex_candidates(text)
    quoted_hits = _quoted_candidates(text)
    list_hits = _list_table_candidates(text)

    names = seeds | alias_hits | hanlp_entities | ltp_entities | regex_hits | quoted_hits | list_hits
    names |= _expand_subtokens(names)

    return [
        EntityCandidate(
            name=n,
            source=_candidate_source(n, seeds, hanlp_entities, ltp_entities, regex_hits, quoted_hits, list_hits)
        )
        for n in names
    ]


def _seed_primary(primary_brand: str, aliases: Dict[str, List[str]]) -> Set[str]:
    """Generate seed entities from primary brand and aliases."""
    seeds = {primary_brand.strip()} if primary_brand else set()
    for lang_aliases in aliases.values():
        for alias in lang_aliases:
            alias_clean = alias.strip()
            if alias_clean:
                seeds.add(alias_clean)
    return seeds


def _extract_with_hanlp(text: str) -> Set[str]:
    """Extract entities using HanLP if available."""
    hanlp = _load_optional_model("hanlp", "hanlp.load")
    if not hanlp:
        return set()
    try:
        model = hanlp("NER/MSRA")
        result = model(text)
        return {item[0] for item in result}
    except Exception:
        return set()


def _extract_with_ltp(text: str) -> Set[str]:
    """Extract entities using LTP if available."""
    ltp_class = _load_optional_model("ltp", "LTP")
    if not ltp_class:
        return set()
    try:
        ltp_instance = ltp_class()
        output = ltp_instance.ner([text])
        return {text[start:end] for _, start, end in output[0]}
    except Exception:
        return set()


def _regex_candidates(text: str) -> Set[str]:
    """Extract candidates using regex patterns."""
    latin_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]{0,9}\d[\w.\-]*)", text)
    model_variants = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]{2,}[\-]?[A-Z0-9])", text)
    model_words = re.findall(r"(?:^|[\s\u4e00-\u9fff])(Model\s?[A-Z0-9]+)", text)
    id_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])(ID\.\d+)", text)

    chinese_digit_suffix = re.findall(r"([\u4e00-\u9fff]{2,6}\d{1,3}\s+(?:Pro|Max|Plus|Ultra|Mini|DM-i|DM-p|EV))", text)
    chinese_suffix = re.findall(r"([\u4e00-\u9fff]{1,6}(?:PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p|EV))", text)
    chinese_digits = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]?\d{1,3})", text)
    chinese_latin = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]{1,3}\d?)", text)
    chinese_brands = re.findall(r"([\u4e00-\u9fff]{2,8}(?!的|了|是|在|和|与|等|个|为|有|将|被))", text)

    latin_suffix = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]+(?:PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p))", text)
    product_lines = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-zÀ-ÿ']+(?:\s+[A-Z][A-Za-zÀ-ÿ']+){1,2})", text)
    mixed_case = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][a-z]+[A-Z][a-z]+)", text)
    latin_with_space = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]+\s+\d+(?:\s+[A-Z][a-z]+)?)", text)
    multiword_latin_number = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+\d+)", text)
    standalone_latin = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]{2,15})(?:\s|[\u4e00-\u9fff]|$)", text)

    digit_prefix_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]\d+[A-Za-z]*)", text)
    letter_digit_combo = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]{1,3}\d{1,4}[A-Za-z]*)", text)
    digit_first_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])(\d+[A-Z][A-Za-z]+)", text)

    hits = (latin_models + model_variants + model_words + id_models +
            chinese_digit_suffix + chinese_suffix + chinese_digits + chinese_latin + chinese_brands +
            latin_suffix + product_lines + mixed_case + latin_with_space + multiword_latin_number +
            standalone_latin + digit_prefix_models + letter_digit_combo + digit_first_models)

    return {n.strip() for n in hits if n.strip() and len(n.strip()) >= 2}


def _quoted_candidates(text: str) -> Set[str]:
    """Extract quoted candidates from text."""
    quoted = re.findall(r'["\'"《》【】([]([^"\'"《》【】)\]]{2,15})["\'"》】)\]]', text)
    hits = set()
    for q in quoted:
        q_stripped = q.strip()
        if 2 <= len(q_stripped) <= 15:
            if not re.search(r"[、，。！？：；]", q_stripped):
                hits.add(q_stripped)
    return hits


def _list_table_candidates(text: str) -> Set[str]:
    """Extract candidates from list and table formats."""
    hits = set()

    numbered_items = re.findall(r'^\s*\d+[\.、\)]\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s\-]{1,30}?)[\s\-:]', text, re.MULTILINE)
    hits.update(numbered_items)

    bulleted_items = re.findall(r'^\s*[-•·]\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s\-]{1,30}?)[\s\-:]', text, re.MULTILINE)
    hits.update(bulleted_items)

    inline_numbered = re.findall(r'\d+[\.、]\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s]{1,20}?)[\s\-:]', text)
    hits.update(inline_numbered)

    brand_mentions = re.findall(r'(?:品牌|推荐|产品|型号)[:：]\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s]{2,20})', text)
    hits.update(brand_mentions)

    cleaned = set()
    for item in hits:
        item_clean = item.strip()
        if 2 <= len(item_clean) <= 30:
            parts = re.split(r'\s+', item_clean)
            for part in parts:
                if len(part) >= 2:
                    cleaned.add(part)
            if len(parts) <= 3:
                cleaned.add(item_clean)

    return cleaned


def _candidate_source(
    name: str,
    seeds: Set[str],
    hanlp: Set[str],
    ltp: Set[str],
    regex_hits: Set[str],
    quoted_hits: Set[str],
    list_hits: Set[str]
) -> str:
    """Determine the source of a candidate."""
    if name in seeds:
        return "seed"
    if name in hanlp:
        return "hanlp"
    if name in ltp:
        return "ltp"
    if name in regex_hits:
        return "regex"
    if name in quoted_hits:
        return "quoted"
    if name in list_hits:
        return "list"
    return "unknown"


def _expand_subtokens(names: Set[str]) -> Set[str]:
    """Expand names into subtokens."""
    expanded: Set[str] = set()
    for name in names:
        expanded.update(re.findall(r"[A-Za-z]{1,10}\.?\d[\w.\-]*", name))
        expanded.update(re.findall(r"Model\s?[A-Za-z0-9]+", name))
    return {token for token in expanded if token}


def _default_alias_table() -> Dict[str, str]:
    """Get default alias table."""
    aliases = {
        "大众": "大众",
        "大眾": "大众",
        "Volkswagen": "大众",
        "VW": "大众",
        "上汽大众": "大众",
        "一汽大众": "大众",
        "丰田": "丰田",
        "Toyota": "丰田",
        "特斯拉": "特斯拉",
        "Tesla": "特斯拉",
        "比亚迪": "比亚迪",
        "BYD": "比亚迪",
    }
    products = {
        "宋PLUS": "宋PLUS",
        "宋Plus": "宋PLUS",
        "宋PlusDM-i": "宋PLUS",
        "ID.4": "ID.4",
        "ModelY": "ModelY",
        "Model Y": "ModelY",
    }
    aliases.update(products)
    return aliases


def _alias_hits(text: str, alias_table: Dict[str, str]) -> Set[str]:
    """Find alias hits in text."""
    hits = set()
    for alias in alias_table.keys():
        if alias and alias in text:
            hits.add(alias)
    return hits


def _load_optional_model(module_name: str, attr: str):
    """Load an optional module if available."""
    module = importlib.util.find_spec(module_name)
    if not module:
        return None
    module_obj = importlib.import_module(module_name)
    return getattr(module_obj, attr, None)
