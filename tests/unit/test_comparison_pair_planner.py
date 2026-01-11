from services.comparison_prompts.pair_planner import build_competitor_brand_schedule


def test_build_competitor_brand_schedule_fails_when_too_few_brands():
    schedule = build_competitor_brand_schedule([2, 3, 4, 5, 6, 7], total=20, max_per_brand=3)
    assert schedule == []


def test_build_competitor_brand_schedule_respects_cap_and_total():
    schedule = build_competitor_brand_schedule([2, 3, 4, 5, 6, 7, 8], total=20, max_per_brand=3)
    assert len(schedule) == 20
    assert max(schedule.count(b) for b in set(schedule)) <= 3


def test_build_competitor_brand_schedule_is_deterministic():
    schedule = build_competitor_brand_schedule([2, 3, 4, 5, 6, 7, 8], total=6, max_per_brand=3)
    assert schedule == [2, 2, 2, 3, 3, 3]

