from __future__ import annotations

from dataclasses import dataclass

from models.domain import LLMRoute
from services.remote_llms import DeepSeekService, KimiService, OpenRouterService


@dataclass(frozen=True)
class ResolvedAuditModel:
    requested_provider: str
    requested_model: str
    resolved_provider: str
    resolved_model: str
    resolved_route: str


def resolve_audit_model(db, provider: str | None, model_name: str | None) -> ResolvedAuditModel:
    requested_provider, requested_model = _defaults(provider, model_name)
    resolved_provider, resolved_model = _resolve_provider_model(db, requested_provider, requested_model)
    route = LLMRoute.OPENROUTER.value if resolved_provider == "openrouter" else LLMRoute.VENDOR.value
    return ResolvedAuditModel(requested_provider, requested_model, resolved_provider, resolved_model, route)


def _defaults(provider: str | None, model_name: str | None) -> tuple[str, str]:
    return (provider or "deepseek").lower(), (model_name or "deepseek-reasoner").strip()


def _resolve_provider_model(db, provider: str, model_name: str) -> tuple[str, str]:
    if provider == "openrouter":
        _require_openrouter(db)
        return provider, model_name or "openrouter/auto"
    if provider == "deepseek" and _has_deepseek(db, model_name):
        return provider, model_name
    if provider == "kimi" and _has_kimi(db):
        return provider, model_name or KimiService.default_model
    _require_openrouter(db)
    return "openrouter", _openrouter_fallback_model(provider, model_name)


def _has_deepseek(db, model: str) -> bool:
    service = DeepSeekService(db)
    service.validate_model(model)
    return service.has_api_key()


def _has_kimi(db) -> bool:
    return KimiService(db).has_api_key()


def _require_openrouter(db) -> None:
    if not OpenRouterService(db).has_api_key():
        raise ValueError("No active openrouter API key found")


def _openrouter_fallback_model(provider: str, model_name: str) -> str:
    if "/" in (model_name or ""):
        return model_name
    if provider in {"deepseek", "kimi"} and model_name:
        return f"{provider}/{model_name}"
    return "openrouter/auto"
