from services.pricing import calculate_cost


def test_calculate_cost_vendor_route_uses_pricing():
    cost = calculate_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000, route="vendor")
    assert cost == 0.7


def test_calculate_cost_vendor_route_uses_kimi_k25_pricing():
    cost = calculate_cost("kimi", "kimi-k2.5", 1_000_000, 1_000_000, route="vendor")
    assert cost == 25.0


def test_calculate_cost_openrouter_route_returns_zero():
    cost = calculate_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000, route="openrouter")
    assert cost == 0.0
