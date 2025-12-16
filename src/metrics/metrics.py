import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class AnswerMetrics:
    prompt_id: int
    brand: str
    rank: Optional[int]
    sentiment: str


def dcg_weight(rank: Optional[int]) -> float:
    if rank is None or rank < 1:
        return 0.0
    return 1 / math.log2(rank + 1)


def mention_rate(prompt_ids: Sequence[int], mentions: Iterable[AnswerMetrics], brand: str) -> float:
    if not prompt_ids:
        return 0.0
    prompt_hits = {m.prompt_id for m in mentions if m.brand == brand}
    return len(prompt_hits) / len(prompt_ids)


def share_of_voice(mentions: Iterable[AnswerMetrics], brand: str, competitor_brands: Sequence[str]) -> float:
    mention_list = list(mentions)
    brand_pool = set(competitor_brands) | {brand}
    brand_weight = sum(dcg_weight(m.rank) for m in mention_list if m.brand == brand)
    total_weight = sum(dcg_weight(m.rank) for m in mention_list if m.brand in brand_pool)
    if brand_weight == 0.0 or total_weight == 0.0:
        return 0.0
    return brand_weight / total_weight


def top_spot_share(prompt_ids: Sequence[int], mentions: Iterable[AnswerMetrics], brand: str) -> float:
    if not prompt_ids:
        return 0.0
    first_place = {m.prompt_id for m in mentions if m.brand == brand and m.rank == 1}
    return len(first_place) / len(prompt_ids)


def sentiment_index(mentions: Iterable[AnswerMetrics], brand: str) -> float:
    brand_mentions = [m for m in mentions if m.brand == brand]
    if not brand_mentions:
        return 0.0
    positives = [m for m in brand_mentions if m.sentiment == "positive"]
    return len(positives) / len(brand_mentions)


def dragon_lens_visibility_score(sov: float, top_spot: float, sentiment: float) -> float:
    return 0.6 * sov + 0.2 * top_spot + 0.2 * sentiment


def zero_metrics() -> Dict[str, float]:
    return {
        "mention_rate": 0.0,
        "share_of_voice": 0.0,
        "top_spot_share": 0.0,
        "sentiment_index": 0.0,
        "dragon_lens_visibility": 0.0,
    }


def build_metric_summary(
    mention_value: float, sov_value: float, top_value: float, sentiment_value: float
) -> Dict[str, float]:
    return {
        "mention_rate": mention_value,
        "share_of_voice": sov_value,
        "top_spot_share": top_value,
        "sentiment_index": sentiment_value,
        "dragon_lens_visibility": dragon_lens_visibility_score(
            sov_value, top_value, sentiment_value
        ),
    }


def visibility_metrics(
    prompt_ids: Sequence[int],
    mentions: Iterable[AnswerMetrics],
    brand: str,
    competitor_brands: Sequence[str],
) -> Dict[str, float]:
    mention_list = list(mentions)
    brand_mentions = [m for m in mention_list if m.brand == brand]
    if not brand_mentions:
        return zero_metrics()

    mention_value = mention_rate(prompt_ids, brand_mentions, brand)
    sov_value = share_of_voice(mention_list, brand, competitor_brands)
    top_value = top_spot_share(prompt_ids, brand_mentions, brand)
    sentiment_value = sentiment_index(brand_mentions, brand)
    return build_metric_summary(mention_value, sov_value, top_value, sentiment_value)
