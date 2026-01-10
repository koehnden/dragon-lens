from __future__ import annotations


def base_generation_count(target_count: int, user_prompt_count: int) -> int:
    return max(0, int(target_count) - int(user_prompt_count))


def competitor_missing_counts(
    competitor_names: list[str],
    existing_counts: dict[str, int],
    min_per_competitor: int,
) -> dict[str, int]:
    minimum = max(0, int(min_per_competitor))
    return {c: max(0, minimum - int(existing_counts.get(c, 0))) for c in competitor_names if c}


def total_generation_count(
    target_count: int,
    user_prompt_count: int,
    missing_by_competitor: dict[str, int],
) -> int:
    base = base_generation_count(target_count, user_prompt_count)
    needed = sum(int(v) for v in (missing_by_competitor or {}).values())
    return max(base, needed)
