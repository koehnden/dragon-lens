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
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "BAAI/bge-m3"
)
EMBEDDING_MODEL_LOAD_TIMEOUT = int(os.getenv("EMBEDDING_MODEL_LOAD_TIMEOUT", "10"))


@dataclass
class EntityCandidate:
    name: str
    source: str


def normalize_text_for_ner(text: str) -> str:
    if not text:
        return text

    normalized = text

    fullwidth_to_halfwidth = {
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
        'Ａ': 'A', 'Ｂ': 'B', 'Ｃ': 'C', 'Ｄ': 'D', 'Ｅ': 'E',
        'Ｆ': 'F', 'Ｇ': 'G', 'Ｈ': 'H', 'Ｉ': 'I', 'Ｊ': 'J',
        'Ｋ': 'K', 'Ｌ': 'L', 'Ｍ': 'M', 'Ｎ': 'N', 'Ｏ': 'O',
        'Ｐ': 'P', 'Ｑ': 'Q', 'Ｒ': 'R', 'Ｓ': 'S', 'Ｔ': 'T',
        'Ｕ': 'U', 'Ｖ': 'V', 'Ｗ': 'W', 'Ｘ': 'X', 'Ｙ': 'Y',
        'Ｚ': 'Z',
        'ａ': 'a', 'ｂ': 'b', 'ｃ': 'c', 'ｄ': 'd', 'ｅ': 'e',
        'ｆ': 'f', 'ｇ': 'g', 'ｈ': 'h', 'ｉ': 'i', 'ｊ': 'j',
        'ｋ': 'k', 'ｌ': 'l', 'ｍ': 'm', 'ｎ': 'n', 'ｏ': 'o',
        'ｐ': 'p', 'ｑ': 'q', 'ｒ': 'r', 'ｓ': 's', 'ｔ': 't',
        'ｕ': 'u', 'ｖ': 'v', 'ｗ': 'w', 'ｘ': 'x', 'ｙ': 'y',
        'ｚ': 'z',
        '　': ' ', '（': '(', '）': ')', '［': '[', '］': ']',
        '｛': '{', '｝': '}', '＜': '<', '＞': '>',
        '＋': '+', '－': '-', '＝': '=', '＊': '*', '／': '/',
        '＆': '&', '％': '%', '＄': '$', '＃': '#', '＠': '@',
        '！': '!', '？': '?', '．': '.', '，': ',', '：': ':',
        '；': ';', '｜': '|', '～': '~', '＿': '_',
    }

    for fullwidth, halfwidth in fullwidth_to_halfwidth.items():
        normalized = normalized.replace(fullwidth, halfwidth)

    chinese_punct_map = {
        '，': ',', '。': '.', '！': '!', '？': '?',
        '：': ':', '；': ';', '、': ',',
        '"': '"', '"': '"', ''': "'", ''': "'",
        '「': '"', '」': '"', '『': '"', '』': '"',
        '【': '[', '】': ']', '《': '<', '》': '>',
        '—': '-', '…': '...',
    }

    for chinese_punct, ascii_punct in chinese_punct_map.items():
        normalized = normalized.replace(chinese_punct, ascii_punct)

    normalized = normalized.replace('\u3000', ' ')
    normalized = normalized.replace('\xa0', ' ')

    normalized = ' '.join(normalized.split())

    return normalized


def extract_entities(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> Dict[str, List[str]]:
    normalized_text = normalize_text_for_ner(text)
    candidates = generate_candidates(normalized_text, primary_brand, aliases)

    if ENABLE_QWEN_FILTERING:
        filtered_candidates = _run_async(_filter_candidates_with_qwen(candidates, normalized_text))
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


async def _filter_candidates_with_qwen(candidates: List[EntityCandidate], text: str) -> List[EntityCandidate]:
    from services.ollama import OllamaService

    ollama = OllamaService()
    filtered = []

    for candidate in candidates:
        if candidate.source == "seed":
            filtered.append(candidate)
            continue

        verification = await _verify_entity_with_qwen(ollama, candidate.name, text)
        if verification and verification.get("type") in ["brand", "product"]:
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


def _contains_feature_keywords(name: str) -> bool:
    keywords = [
        "动力",
        "天窗",
        "后备箱",
        "品牌口碑",
        "舒适",
        "空间",
        "配置",
        "自动驾驶",
        "主动安全",
        "车机系统",
        "发动机",
        "变速箱",
        "维修"
    ]
    return any(keyword in name for keyword in keywords)


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
        r"[\u4e00-\u9fff]+量$",
        r"(效果|功能|特点|优点|缺点|成分|配置|体验|表现|质地|口感|触感)",
        r"(空间|时间|速度|距离|重量|容量|尺寸|含量|纯度|亮度|硬度|粘度)",
        r"(良好|优秀|出色|卓越|强劲|轻薄|厚重|柔软|坚固|充足|丰富|均衡)",
        r"(大小|高低|长短|粗细|厚薄)",
        r"^更[\u4e00-\u9fff]+$",
        r"^很[\u4e00-\u9fff]+$",
        r"^非常[\u4e00-\u9fff]+$",
        r"(舒适|保暖|透气|耐用|防水|防滑)",
        r"^[\u4e00-\u9fff]{7,}$",
    ]

    for pattern in feature_descriptor_patterns:
        if re.search(pattern, name):
            return False

    if _contains_feature_keywords(name):
        return False

    generic_stop_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "品牌", "产品", "类型", "种类", "系列", "排行",
        "国产", "进口", "豪华", "高端", "入门", "国产品牌",
        "安全性", "可靠性", "舒适性", "性价比", "适口性",
        "猫粮", "狗粮", "补剂", "胶原蛋白",
        "扫地机", "吸尘器", "处方粮",
        "温和性好", "性价比高", "肤感舒适", "适合敏感肌",
    }

    if name.lower() in {w.lower() for w in generic_stop_words}:
        return False

    compound_descriptor_endings = ["高", "好", "强", "差", "低", "等", "改善", "提升", "规划", "方面", "指标"]
    if len(name) > 2 and any(name.endswith(ending) for ending in compound_descriptor_endings):
        has_brand_pattern = any(re.search(pattern, name) for pattern in [
            r"[A-Za-z]+",
            r"\d+",
            r"(PLUS|Plus|Pro|Max|Ultra|Mini|DM-i)"
        ])
        if not has_brand_pattern:
            return False

    if len(name) > 4 and any(keyword in name for keyword in ["推荐", "适合", "保湿", "消化", "粪便", "噪音", "品质", "安全性", "操作", "智能"]):
        return False

    if re.search(r"[、，。！？：；]", name):
        return False

    brand_product_patterns = [
        r"^[A-Z]{2,}[\-]?[A-Z0-9]*$",
        r"[A-Za-z]+\d+",
        r"\d+[A-Za-z]+",
        r"Model\s?[A-ZX0-9]",
        r"ID\.",
        r"[\u4e00-\u9fff]{1,6}(PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p|EV)",
        r"[\u4e00-\u9fff]{2,6}\d{1,3}\s+(Pro|Max|Plus|Ultra|Mini|DM-i|DM-p|EV)",
        r"[\u4e00-\u9fff]{2,6}[A-Z]\d{1,2}",
        r"[\u4e00-\u9fff]{2,6}\d{1,3}",
        r"^[\u4e00-\u9fff]{2,8}$",
        r"^[A-Za-z]{2,}$",
        r"[A-Za-z]{2,}[\u4e00-\u9fff]+",
        r"[\u4e00-\u9fff]+[A-Za-z]{2,}",
        r"[A-Z][a-z]+[A-Z]",
        r"[A-Z][a-z]+\s+\d+",
        r"[A-Z][a-z]+\s+[A-Z][a-z]+(\s+\d+)?",
        r"[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+",
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
        if best_option != normalized:
            if _has_variant_signals(normalized) and not _has_variant_signals(best_option):
                logger.debug(f"Merge constraint (fuzzy): '{normalized}' has variant signals, '{best_option}' doesn't - skipping merge")
                return None

            if len(normalized) > len(best_option) and best_option in normalized:
                suffix = normalized[len(best_option):]
                if _has_variant_signals(suffix):
                    logger.debug(f"Merge constraint (fuzzy): suffix '{suffix}' has variant signals - skipping merge")
                    return None

        return lookup[best_option]
    return None


async def _verify_entity_with_qwen(ollama, name: str, text: str) -> Dict | None:
    import json

    evidence = _extract_evidence(name, text)
    if not evidence:
        logger.warning(f"No evidence found for '{name}' in text")
        return None

    system_prompt = """You are a brand recognition expert. Analyze the provided candidate entity ONLY based on the evidence from the source text.

CRITICAL RULES:
1. DO NOT invent or hallucinate entities not in the candidate or evidence
2. Base your classification ONLY on the provided evidence snippet
3. Output ONLY valid JSON in the exact format specified

Classify the entity as:
- "brand": A brand/company name (e.g., 比亚迪, Tesla, Loreal)
- "product": A specific product/model name (e.g., 宋PLUS, iPhone14, Mate50)
- "other": Feature descriptions, quality descriptors, generic terms (e.g., 保湿效果, 性价比, 空间)

Output format (JSON only, no additional text):
{
  "type": "brand|product|other",
  "canonical_guess": "normalized form (optional)",
  "confidence": 0.0-1.0,
  "why": "one short reason"
}"""

    prompt = f"""Candidate: "{name}"

Evidence from text:
{evidence['snippet']}

Offsets: character {evidence['start']}-{evidence['end']}

Classify this candidate based ONLY on the evidence above. Output JSON only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        result = _parse_json_response(response)
        if not result:
            logger.warning(f"Failed to parse JSON for '{name}': {response[:100]}")
            return None

        required_fields = ["type", "confidence", "why"]
        if not all(field in result for field in required_fields):
            logger.warning(f"Missing required fields in response for '{name}': {result}")
            return None

        if result["type"] not in ["brand", "product", "other"]:
            logger.warning(f"Invalid type '{result['type']}' for '{name}'")
            return None

        return result

    except Exception as e:
        logger.warning(f"Qwen verification failed for '{name}': {e}")
        return None


def _extract_evidence(name: str, text: str, context_chars: int = 50) -> Dict | None:
    name_lower = name.lower()
    text_lower = text.lower()

    start_pos = text_lower.find(name_lower)
    if start_pos == -1:
        return None

    end_pos = start_pos + len(name)

    snippet_start = max(0, start_pos - context_chars)
    snippet_end = min(len(text), end_pos + context_chars)

    snippet = text[snippet_start:snippet_end]

    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet = snippet + "..."

    return {
        "snippet": snippet,
        "start": start_pos,
        "end": end_pos,
        "mention": text[start_pos:end_pos]
    }


def _parse_json_response(response: str) -> Dict | None:
    import json

    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    return None


def _load_embedding_model_sync(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


async def _load_embedding_model(model_name: str, timeout_seconds: int):
    loop = asyncio.get_running_loop()
    loader = loop.run_in_executor(None, _load_embedding_model_sync, model_name)
    return await asyncio.wait_for(loader, timeout_seconds)


async def _cluster_with_embeddings(candidates: List[EntityCandidate]) -> Dict[str, List[EntityCandidate]]:
    if not candidates:
        return {}

    try:
        model = await _load_embedding_model(
            EMBEDDING_MODEL_NAME,
            EMBEDDING_MODEL_LOAD_TIMEOUT
        )

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

    hits = (latin_models + model_variants + model_words + id_models +
            chinese_digit_suffix + chinese_suffix + chinese_digits + chinese_latin + chinese_brands +
            latin_suffix + product_lines + mixed_case + latin_with_space + multiword_latin_number +
            standalone_latin + digit_prefix_models + letter_digit_combo)

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


def _list_table_candidates(text: str) -> Set[str]:
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


def _candidate_source(name: str, seeds: Set[str], hanlp: Set[str], ltp: Set[str], regex_hits: Set[str], quoted_hits: Set[str], list_hits: Set[str]) -> str:
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


def _has_variant_signals(text: str) -> bool:
    if not text or len(text) < 2:
        return False

    text_lower = text.lower()

    if re.search(r'\d', text):
        return True

    trim_markers = [
        'pro', 'max', 'plus', 'ultra', 'mini',
        'dm-i', 'dm-p', 'ev', 'phev', 'bev',
        'sport', 'luxury', 'premium', 'elite',
        'performance'
    ]
    if any(marker in text_lower for marker in trim_markers):
        return True

    if 'longrange' in text_lower or 'long range' in text_lower:
        return True
    if 'standardrange' in text_lower or 'standard range' in text_lower:
        return True

    capacity_size_patterns = [
        r'\d+\s*[gt]b?',
        r'\d+\s*英寸',
        r'\d+\s*寸',
        r'\d+\.?\d*\s*[lt]',
        r'\d+\s*mah',
        r'\d+\s*w',
    ]
    if any(re.search(pattern, text_lower) for pattern in capacity_size_patterns):
        return True

    return False


def _match_substring_alias(normalized: str, lookup: Dict[str, str]) -> str | None:
    for alias_norm, canonical in lookup.items():
        if not alias_norm or alias_norm not in normalized:
            continue

        if alias_norm == normalized:
            return canonical

        if _has_variant_signals(normalized) and not _has_variant_signals(alias_norm):
            logger.debug(f"Merge constraint: '{normalized}' has variant signals, '{alias_norm}' doesn't - skipping merge")
            continue

        if len(normalized) > len(alias_norm):
            suffix = normalized[len(alias_norm):]
            if _has_variant_signals(suffix):
                logger.debug(f"Merge constraint: suffix '{suffix}' of '{normalized}' has variant signals - skipping merge")
                continue

        logger.debug(f"Allowing merge: '{normalized}' -> '{canonical}' via alias '{alias_norm}'")
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


def canonicalize_entities(candidates: List[EntityCandidate], primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str] | None = None, text: str = "") -> Dict[str, List[str]]:
    if ENABLE_QWEN_FILTERING and text:
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
