from models.domain import LLMProvider

PRICING = {
    LLMProvider.QWEN: {},
    LLMProvider.DEEPSEEK: {
        "deepseek-chat": {"input": 0.14, "output": 0.28, "unit": 1_000_000},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19, "unit": 1_000_000},
    },
    LLMProvider.KIMI: {
        "moonshot-v1-8k": {"input": 0.012, "output": 0.012, "unit": 1000},
        "moonshot-v1-32k": {"input": 0.024, "output": 0.024, "unit": 1000},
        "moonshot-v1-128k": {"input": 0.06, "output": 0.06, "unit": 1000},
    },
}


def _normalize_route(route: str | None) -> str | None:
    if route is None:
        return None
    if hasattr(route, "value"):
        return route.value
    return str(route)


def calculate_cost(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    route: str | None = None,
) -> float:
    route_value = _normalize_route(route)
    if route_value and route_value.lower() == "openrouter":
        return 0.0
    try:
        provider_enum = LLMProvider(provider.lower())
    except ValueError:
        return 0.0

    provider_pricing = PRICING.get(provider_enum, {})
    if not provider_pricing:
        return 0.0

    model_pricing = provider_pricing.get(model.lower())
    if not model_pricing:
        return 0.0

    unit = model_pricing["unit"]
    cost_in = (tokens_in / unit) * model_pricing["input"]
    cost_out = (tokens_out / unit) * model_pricing["output"]
    return round(cost_in + cost_out, 6)
