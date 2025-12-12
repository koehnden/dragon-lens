import importlib
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Set


@dataclass
class EntityCandidate:
    name: str
    source: str


def generate_candidates(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> List[EntityCandidate]:
    seeds = _seed_primary(primary_brand, aliases)
    alias_hits = _alias_hits(text, _default_alias_table())
    hanlp_entities = _extract_with_hanlp(text)
    ltp_entities = _extract_with_ltp(text)
    regex_hits = _regex_candidates(text)
    quoted_hits = _quoted_candidates(text)
    names = seeds | alias_hits | hanlp_entities | ltp_entities | regex_hits | quoted_hits
    names |= _expand_subtokens(names)
    return [EntityCandidate(name=n, source=_candidate_source(n, seeds, hanlp_entities, ltp_entities, regex_hits, quoted_hits)) for n in names]


def canonicalize_entities(candidates: List[EntityCandidate], primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str] | None = None) -> Dict[str, List[str]]:
    alias_table = alias_table or _default_alias_table()
    normalized_aliases = _build_alias_lookup(primary_brand, aliases, alias_table)
    clusters: Dict[str, Set[str]] = {}
    for candidate in candidates:
        normalized = _normalize_text(candidate.name)
        canonical = normalized_aliases.get(normalized) or _match_substring_alias(normalized, normalized_aliases)
        canonical = canonical or _fuzzy_match(normalized, normalized_aliases)
        canonical = canonical or normalized
        clusters.setdefault(canonical, set()).add(candidate.name)
    return {k: sorted(v) for k, v in clusters.items() if k}


def extract_entities(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> Dict[str, List[str]]:
    candidates = generate_candidates(text, primary_brand, aliases)
    return canonicalize_entities(candidates, primary_brand, aliases)


def _seed_primary(primary_brand: str, aliases: Dict[str, List[str]]) -> Set[str]:
    seeds = {primary_brand.strip()} if primary_brand else set()
    for lang_aliases in aliases.values():
        for alias in lang_aliases:
            alias_clean = alias.strip()
            if alias_clean:
                seeds.add(alias_clean)
    return seeds


def _extract_with_hanlp(text: str) -> Set[str]:
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
    latin_models = re.findall(r"[A-Za-z]{1,10}\s?[A-Za-z]?\d[\w.\-]*", text)
    model_words = re.findall(r"Model\s?[A-Za-z0-9]+", text)
    chinese_suffix = re.findall(r"[\u4e00-\u9fff]{1,6}[A-Za-z]*\d{0,3}(?:PLUS|Plus|Pro|Max|DM-i|DM-I)?", text)
    mixed_names = re.findall(r"[\u4e00-\u9fff]{1,4}[A-Za-z]{2,}\s?[A-Za-z0-9\-\.]{0,5}", text)
    combo = re.findall(r"[A-Za-z\u4e00-\u9fff]{2,}[\-·•]{0,1}[A-Za-z\u4e00-\u9fff\d]{1,}", text)
    hits = latin_models + model_words + chinese_suffix + mixed_names + combo
    return {n.strip() for n in hits if n.strip()}


def _quoted_candidates(text: str) -> Set[str]:
    quoted = re.findall(r"[\"\'“”‘’《》【】\(\[]([^\"\'“”‘’《》【】\)\]]{2,20})[\"\'“”‘’》】\)\]]", text)
    rows = re.findall(r"(?:^|\n)[\-•·]?\s*([\u4e00-\u9fffA-Za-z0-9][^\n]{1,20})", text)
    hits = {q.strip() for q in quoted + rows if q.strip()}
    return {h for h in hits if len(h) <= 30}


def _candidate_source(name: str, seeds: Set[str], hanlp: Set[str], ltp: Set[str], regex_hits: Set[str], quoted_hits: Set[str]) -> str:
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
    return "unknown"


def _normalize_text(value: str) -> str:
    simplified = _convert_to_simplified(value)
    folded = unicodedata.normalize("NFKC", simplified).lower()
    stripped = re.sub(r"[\s\W·•\-_/]+", "", folded)
    return stripped


def _expand_subtokens(names: Set[str]) -> Set[str]:
    expanded: Set[str] = set()
    for name in names:
        expanded.update(re.findall(r"[A-Za-z]{1,10}\.?\d[\w.\-]*", name))
        expanded.update(re.findall(r"Model\s?[A-Za-z0-9]+", name))
    return {token for token in expanded if token}


def _convert_to_simplified(value: str) -> str:
    converter = _load_optional_model("opencc", "OpenCC")
    if not converter:
        return value
    try:
        return converter("t2s").convert(value)
    except Exception:
        return value


def _build_alias_lookup(primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    canonical_primary = _normalize_text(primary_brand)
    if canonical_primary:
        lookup[canonical_primary] = canonical_primary
    for alias_list in aliases.values():
        for alias in alias_list:
            normalized = _normalize_text(alias)
            if normalized:
                lookup[normalized] = canonical_primary
    for alias, canonical in alias_table.items():
        normalized_alias = _normalize_text(alias)
        normalized_canonical = _normalize_text(canonical)
        if normalized_alias and normalized_canonical:
            lookup[normalized_alias] = normalized_canonical
    return lookup


def _match_substring_alias(normalized: str, lookup: Dict[str, str]) -> str | None:
    for alias_norm, canonical in lookup.items():
        if alias_norm and alias_norm in normalized:
            return canonical
    return None


def _fuzzy_match(normalized: str, lookup: Dict[str, str]) -> str | None:
    candidates = list(lookup.keys())
    if not candidates:
        return None
    scores = [(SequenceMatcher(a=normalized, b=option).ratio(), option) for option in candidates]
    best_score, best_option = max(scores, key=lambda item: item[0])
    if best_score >= 0.82:
        return lookup[best_option]
    return None


def _default_alias_table() -> Dict[str, str]:
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
    hits = set()
    for alias in alias_table.keys():
        if alias and alias in text:
            hits.add(alias)
    return hits


def _load_optional_model(module_name: str, attr: str):
    module = importlib.util.find_spec(module_name)
    if not module:
        return None
    module_obj = importlib.import_module(module_name)
    return getattr(module_obj, attr, None)
