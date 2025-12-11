from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class AnswerMetrics:
    prompt_id: int
    brand: str
    rank: Optional[int]
    sentiment: str


def mention_weight(rank: Optional[int]) -> float:
    if rank is None or rank < 1:
        return 0.0
    score = 1 - 0.3 * (rank - 1)
    score = score if score > 0 else 0.0
    return round(score, 10)


def brand_mentions(mentions: Iterable[AnswerMetrics], brand: str) -> List[AnswerMetrics]:
    return [mention for mention in mentions if mention.brand == brand]


def brand_mentions_for_prompt(mentions: Iterable[AnswerMetrics], prompt_id: int) -> List[AnswerMetrics]:
    return [mention for mention in mentions if mention.prompt_id == prompt_id]


def prompts_with_brand(mentions: Iterable[AnswerMetrics], brand: str) -> int:
    return len({mention.prompt_id for mention in mentions if mention.brand == brand})


def asov_coverage(prompt_ids: Sequence[int], mentions: Iterable[AnswerMetrics], brand: str) -> float:
    total_prompts = len(prompt_ids)
    if total_prompts == 0:
        return 0.0
    return prompts_with_brand(mentions, brand) / total_prompts


def asov_relative(mentions: Iterable[AnswerMetrics], brand: str) -> float:
    mentions_list = list(mentions)
    if not mentions_list:
        return 0.0
    brand_total = len(brand_mentions(mentions_list, brand))
    return brand_total / len(mentions_list)


def prominence_score(
    mentions: Iterable[AnswerMetrics],
    brand: str,
    weight_func: Callable[[Optional[int]], float] = mention_weight,
) -> float:
    brand_mentions_list = [mention for mention in mentions if mention.brand == brand and mention.rank]
    if not brand_mentions_list:
        return 0.0
    weights = [weight_func(mention.rank) for mention in brand_mentions_list]
    return sum(weights) / len(weights)


def top_spot_share(prompt_ids: Sequence[int], mentions: Iterable[AnswerMetrics], brand: str) -> float:
    total_prompts = len(prompt_ids)
    if total_prompts == 0:
        return 0.0
    prompt_hits = {mention.prompt_id for mention in mentions if mention.brand == brand and mention.rank == 1}
    return len(prompt_hits) / total_prompts


def sentiment_value(sentiment: str) -> float:
    if sentiment == "positive":
        return 1.0
    if sentiment == "negative":
        return -1.0
    return 0.0


def sentiment_index(mentions: Iterable[AnswerMetrics], brand: str) -> float:
    brand_mentions_list = brand_mentions(mentions, brand)
    if not brand_mentions_list:
        return 0.0
    scores = [sentiment_value(mention.sentiment) for mention in brand_mentions_list]
    return sum(scores) / len(scores)


def positive_share(mentions: Iterable[AnswerMetrics], brand: str) -> float:
    brand_mentions_list = brand_mentions(mentions, brand)
    if not brand_mentions_list:
        return 0.0
    positives = [mention for mention in brand_mentions_list if mention.sentiment == "positive"]
    return len(positives) / len(brand_mentions_list)


def opportunity_rate(
    prompt_ids: Sequence[int],
    mentions: Iterable[AnswerMetrics],
    brand: str,
    competitor_brands: Sequence[str],
) -> float:
    total_prompts = len(prompt_ids)
    if total_prompts == 0:
        return 0.0
    prompt_to_brands = prompt_brand_index(mentions)
    missing_prompts = [
        pid
        for pid in prompt_ids
        if prompt_competes_without_brand(prompt_to_brands, pid, brand, competitor_brands)
    ]
    return len(missing_prompts) / total_prompts


def dragon_visibility_score(
    coverage: float,
    prominence: float,
    positive: float,
    weights: Sequence[float],
) -> float:
    alpha, beta, gamma = weights
    total_weight = alpha + beta + gamma
    if total_weight == 0:
        return 0.0
    score = alpha * coverage + beta * prominence + gamma * positive
    return (score / total_weight) * 100


def prompt_brand_index(mentions: Iterable[AnswerMetrics]) -> Dict[int, set]:
    index: Dict[int, set] = {}
    for mention in mentions:
        index.setdefault(mention.prompt_id, set()).add(mention.brand)
    return index


def prompt_competes_without_brand(
    prompt_brand_map: Dict[int, set],
    prompt_id: int,
    brand: str,
    competitor_brands: Sequence[str],
) -> bool:
    brands = prompt_brand_map.get(prompt_id, set())
    return brand not in brands and any(cb in brands for cb in competitor_brands)


def metric_scores(
    prompt_ids: Sequence[int],
    mentions: Iterable[AnswerMetrics],
    brand: str,
    competitor_brands: Sequence[str],
    weights: Sequence[float],
) -> tuple[float, float, float, float, float, float, float, float]:
    mentions_list = list(mentions)
    coverage = asov_coverage(prompt_ids, mentions_list, brand)
    relative = asov_relative(mentions_list, brand)
    prominence = prominence_score(mentions_list, brand)
    top_spot = top_spot_share(prompt_ids, mentions_list, brand)
    sentiment = sentiment_index(mentions_list, brand)
    positive = positive_share(mentions_list, brand)
    opportunity = opportunity_rate(prompt_ids, mentions_list, brand, competitor_brands)
    dvs = dragon_visibility_score(coverage, prominence, positive, weights)
    return coverage, relative, prominence, top_spot, sentiment, positive, opportunity, dvs


def visibility_metrics(
    prompt_ids: Sequence[int],
    mentions: Iterable[AnswerMetrics],
    brand: str,
    competitor_brands: Sequence[str],
    weights: Sequence[float] = (0.4, 0.4, 0.2),
) -> Dict[str, float]:
    (
        coverage,
        relative,
        prominence,
        top_spot,
        sentiment,
        positive,
        opportunity,
        dvs,
    ) = metric_scores(prompt_ids, mentions, brand, competitor_brands, weights)
    return {
        "ASoV_coverage": coverage,
        "ASoV_relative": relative,
        "Prominence Score": prominence,
        "Top-Spot Share": top_spot,
        "Sentiment Index": sentiment,
        "Positive Share": positive,
        "Opportunity Rate": opportunity,
        "Dragon Visibility Score": dvs,
    }
