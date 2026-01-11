from __future__ import annotations


def build_competitor_brand_schedule(brand_ids: list[int], total: int, max_per_brand: int) -> list[int]:
    cap = max(0, int(max_per_brand))
    target = max(0, int(total))
    unique = _unique_ints(brand_ids or [])
    if target > cap * len(unique):
        return []
    return _fill_schedule(unique, target, cap)


def _unique_ints(values: list[int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        i = int(v)
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def _fill_schedule(brand_ids: list[int], total: int, cap: int) -> list[int]:
    out: list[int] = []
    for brand_id in brand_ids:
        out.extend([int(brand_id)] * min(cap, total - len(out)))
        if len(out) >= total:
            return out
    return out
