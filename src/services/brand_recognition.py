import asyncio
import importlib
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ENABLE_QWEN_FILTERING = os.getenv("ENABLE_QWEN_FILTERING", "true").lower() == "true"
ENABLE_EMBEDDING_CLUSTERING = os.getenv("ENABLE_EMBEDDING_CLUSTERING", "true").lower() == "true"
ENABLE_LLM_CLUSTERING = os.getenv("ENABLE_LLM_CLUSTERING", "true").lower() == "true"


@dataclass
class EntityCandidate:
    name: str
    source: str


def extract_entities(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> Dict[str, List[str]]:
    candidates = generate_candidates(text, primary_brand, aliases)

    if ENABLE_QWEN_FILTERING:
        filtered_candidates = _run_async(_filter_candidates_with_qwen(candidates, text))
    else:
        filtered_candidates = _filter_candidates_simple(candidates)

    if ENABLE_EMBEDDING_CLUSTERING:
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    return final_clusters


def generate_candidates(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> List[EntityCandidate]:
    seeds = _seed_primary(primary_brand, aliases)
    alias_hits = _alias_hits(text, _default_alias_table())
    hanlp_entities = _extract_with_hanlp(text)
    ltp_entities = _extract_with_ltp(text)
    regex_hits = _regex_candidates(text)
    quoted_hits = _quoted_candidates(text)

    names = seeds | alias_hits | hanlp_entities | ltp_entities | regex_hits | quoted_hits
    names |= _expand_subtokens(names)

    return [
        EntityCandidate(
            name=n,
            source=_candidate_source(n, seeds, hanlp_entities, ltp_entities, regex_hits, quoted_hits)
        )
        for n in names
    ]


async def _filter_candidates_with_qwen(candidates: List[EntityCandidate]) -> List[EntityCandidate]:
    from services.ollama import OllamaService

    ollama = OllamaService()
    filtered = []

    for candidate in candidates:
        if candidate.source == "seed":
            filtered.append(candidate)
            continue

        is_brand = await _is_brand_or_product_qwen(ollama, candidate.name)
        if is_brand:
            filtered.append(candidate)

    logger.info(f"Qwen filtering: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _filter_candidates_simple(candidates: List[EntityCandidate]) -> List[EntityCandidate]:
    filtered = []
    for candidate in candidates:
        if candidate.source == "seed":
            filtered.append(candidate)
        elif _is_valid_brand_candidate(candidate.name):
            filtered.append(candidate)
    logger.info(f"Simple filtering: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _is_valid_brand_candidate(name: str) -> bool:
    if len(name) < 2 or len(name) > 30:
        return False

    feature_descriptor_patterns = [
        r"等$",
        r"[\u4e00-\u9fff]+度$",
        r"[\u4e00-\u9fff]+性$",
        r"[\u4e00-\u9fff]+率$",
        r"[\u4e00-\u9fff]+感$",
        r"[\u4e00-\u9fff]+力$",
        r"(效果|功能|特点|优点|缺点|成分|配置|体验|表现|质地|口感|触感)",
        r"(空间|时间|速度|距离|重量|容量|尺寸)",
        r"(良好|优秀|出色|卓越|强劲|轻薄|厚重|柔软|坚固)",
        r"^[\u4e00-\u9fff]{5,}$",
    ]

    for pattern in feature_descriptor_patterns:
        if re.search(pattern, name):
            return False

    generic_stop_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "品牌", "产品", "类型", "种类", "系列",
        "国产", "进口", "豪华", "高端", "入门",
        "安全性", "可靠性", "舒适性", "性价比",
    }
    if name in generic_stop_words:
        return False

    if re.search(r"[、，。！？：；]", name):
        return False

    brand_product_patterns = [
        r"^[A-Z]{2,}[\-]?[A-Z0-9]*$",
        r"[A-Za-z]+\d+",
        r"\d+[A-Za-z]+",
        r"Model\s?[A-ZX0-9]",
        r"ID\.",
        r"[\u4e00-\u9fff]{1,6}(PLUS|Plus|Pro|Max|Ultra|Mini)",
        r"[\u4e00-\u9fff]{2,6}[A-Z]\d{1,2}",
        r"^[\u4e00-\u9fff]{2,6}$",
        r"^[A-Za-z]{2,}$",
    ]

    for pattern in brand_product_patterns:
        if re.search(pattern, name):
            return True

    return False


def _simple_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    from difflib import SequenceMatcher

    normalized_aliases = _build_alias_lookup(primary_brand, aliases, _default_alias_table())
    final_clusters: Dict[str, Set[str]] = {}

    for cluster_key, cluster_members in embedding_clusters.items():
        normalized = _normalize_text(cluster_key)

        canonical = normalized_aliases.get(normalized)
        if not canonical:
            canonical = _match_substring_alias(normalized, normalized_aliases)
        if not canonical:
            canonical = _fuzzy_match(normalized, normalized_aliases)
        if not canonical:
            canonical = normalized

        final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)

    logger.info(f"Simple clustering: {len(embedding_clusters)} clusters -> {len(final_clusters)} final clusters")
    return {k: sorted(v) for k, v in final_clusters.items() if k}


def _fuzzy_match(normalized: str, lookup: Dict[str, str]) -> str | None:
    from difflib import SequenceMatcher

    candidates = list(lookup.keys())
    if not candidates:
        return None
    scores = [(SequenceMatcher(a=normalized, b=option).ratio(), option) for option in candidates]
    best_score, best_option = max(scores, key=lambda item: item[0])
    if best_score >= 0.82:
        return lookup[best_option]
    return None


async def _is_brand_or_product_qwen(ollama, name: str) -> bool:
    system_prompt = """You are a brand recognition expert. Determine if the given text is a brand name or product name.

Answer ONLY with 'YES' if it is a brand or product name.
Answer ONLY with 'NO' if it is a feature description, quality descriptor, or generic term.

Examples:
- "比亚迪" (BYD) -> YES
- "宋PLUS" -> YES
- "iPhone14" -> YES
- "保湿效果" (moisturizing effect) -> NO
- "性价比" (cost performance) -> NO
- "液晶仪表盘" (LCD dashboard) -> NO"""

    prompt = f"Is '{name}' a brand or product name? Answer YES or NO."

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        result = response.strip().upper()
        return "YES" in result or result.startswith("Y")
    except Exception as e:
        logger.warning(f"Qwen filtering failed for '{name}': {e}")
        return True


async def _cluster_with_embeddings(candidates: List[EntityCandidate]) -> Dict[str, List[EntityCandidate]]:
    if not candidates:
        return {}

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer('BAAI/bge-m3')

        names = [c.name for c in candidates]
        embeddings = model.encode(names, normalize_embeddings=True)

        similarity_threshold = 0.85
        clusters = {}
        used = set()

        for i, candidate_i in enumerate(candidates):
            if i in used:
                continue

            cluster_key = candidate_i.name
            cluster_members = [candidate_i]
            used.add(i)

            for j in range(i + 1, len(candidates)):
                if j in used:
                    continue

                similarity = float(np.dot(embeddings[i], embeddings[j]))

                if similarity >= similarity_threshold:
                    cluster_members.append(candidates[j])
                    used.add(j)

            clusters[cluster_key] = cluster_members

        logger.info(f"Embedding clustering: {len(candidates)} candidates -> {len(clusters)} clusters")
        return clusters

    except Exception as e:
        logger.warning(f"Embedding clustering failed: {e}. Falling back to individual candidates.")
        return {c.name: [c] for c in candidates}


async def _llm_assisted_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    from services.ollama import OllamaService

    ollama = OllamaService()
    normalized_aliases = _build_alias_lookup(primary_brand, aliases, _default_alias_table())

    final_clusters: Dict[str, Set[str]] = {}

    for cluster_key, cluster_members in embedding_clusters.items():
        normalized = _normalize_text(cluster_key)

        canonical = normalized_aliases.get(normalized)
        if canonical:
            final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)
            continue

        canonical = _match_substring_alias(normalized, normalized_aliases)
        if canonical:
            final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)
            continue

        if len(cluster_members) == 1:
            final_clusters.setdefault(normalized, set()).add(cluster_members[0].name)
            continue

        verified_canonical = await _verify_cluster_with_qwen(ollama, cluster_members)
        if verified_canonical:
            final_clusters.setdefault(verified_canonical, set()).update(m.name for m in cluster_members)
        else:
            for member in cluster_members:
                final_clusters.setdefault(_normalize_text(member.name), set()).add(member.name)

    return {k: sorted(v) for k, v in final_clusters.items() if k}


async def _verify_cluster_with_qwen(ollama, members: List[EntityCandidate]) -> str | None:
    if len(members) < 2:
        return None

    names_list = [m.name for m in members]
    system_prompt = """You are a brand clustering expert. Determine if the given names refer to the same brand or product.

If they are the same or aliases of each other, respond with the canonical name.
If they are different, respond with 'DIFFERENT'.

Examples:
- Input: ["Tesla", "特斯拉", "特斯拉汽车"]
  Output: Tesla

- Input: ["BYD", "比亚迪", "比亞迪"]
  Output: BYD

- Input: ["Toyota", "Honda"]
  Output: DIFFERENT"""

    prompt = f"Are these the same brand/product? {names_list}\n\nAnswer with the canonical name or 'DIFFERENT':"

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        result = response.strip()
        if "DIFFERENT" in result.upper():
            return None

        return _normalize_text(result)
    except Exception as e:
        logger.warning(f"LLM clustering verification failed: {e}")
        return None


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        raise RuntimeError("Cannot run async code from within async context. Use await instead.")


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
    latin_models = re.findall(r"([A-Z][A-Za-z]{0,9}\d[\w.\-]*)", text)
    model_variants = re.findall(r"([A-Z]{2,}[\-]?[A-Z0-9])", text)
    model_words = re.findall(r"(Model\s?[A-Z0-9]+)", text)
    id_models = re.findall(r"(ID\.\d+)", text)
    chinese_suffix = re.findall(r"([\u4e00-\u9fff]{1,6}(?:PLUS|Plus|Pro|Max|Ultra|Mini))", text)
    chinese_digits = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]?\d{1,3})", text)
    chinese_latin = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]{1,3}\d?)", text)
    product_lines = re.findall(r"([A-Z][A-Za-zÀ-ÿ']+(?:\s+[A-Z][A-Za-zÀ-ÿ']+){1,2})", text)
    mixed_case = re.findall(r"([A-Z][a-z]+[A-Z][a-z]+)", text)
    latin_with_space = re.findall(r"([A-Z][A-Za-z]+\s+\d+(?:\s+[A-Z][a-z]+)?)", text)
    hits = latin_models + model_variants + model_words + id_models + chinese_suffix + chinese_digits + chinese_latin + product_lines + mixed_case + latin_with_space
    return {n.strip() for n in hits if n.strip() and len(n.strip()) >= 2}


def _quoted_candidates(text: str) -> Set[str]:
    quoted = re.findall(r'["\'"《》【】([]([^"\'"《》【】)\]]{2,15})["\'"》】)\]]', text)
    hits = set()
    for q in quoted:
        q_stripped = q.strip()
        if 2 <= len(q_stripped) <= 15:
            if not re.search(r"[、，。！？：；]", q_stripped):
                hits.add(q_stripped)
    return hits


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


def canonicalize_entities(candidates: List[EntityCandidate], primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str] | None = None) -> Dict[str, List[str]]:
    if ENABLE_QWEN_FILTERING:
        filtered_candidates = _run_async(_filter_candidates_with_qwen(candidates))
    else:
        filtered_candidates = _filter_candidates_simple(candidates)

    if ENABLE_EMBEDDING_CLUSTERING:
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    return final_clusters
