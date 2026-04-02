import httpx
import streamlit as st

from config import settings


def api_url(path: str) -> str:
    return f"http://localhost:{settings.api_port}{path}"


def fetch_json(
    path: str, params: dict | None = None, timeout: float = 30.0, silent: bool = False,
) -> dict | list | None:
    try:
        response = httpx.get(api_url(path), params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        if not silent:
            st.error(f"Request failed: {exc}")
        return None


def fetch_verticals() -> list[dict]:
    return fetch_json("/api/v1/verticals", timeout=10.0) or []


def fetch_available_models(vertical_id: int) -> list[str]:
    return fetch_json(f"/api/v1/verticals/{vertical_id}/models", timeout=10.0) or []


def fetch_user_brands(vertical_id: int) -> list[dict]:
    brands = fetch_json(
        f"/api/v1/verticals/{vertical_id}/brands",
        params={"user_input_only": True},
        timeout=10.0,
    )
    return brands or []

_MODEL_SHORT_NAMES: dict[str, str] = {
    "qwen2.5:7b-instruct-q4_0": "Qwen 7B",
    "qwen/qwen-2.5-72b-instruct": "Qwen 72B",
    "qwen/qwen3.5-plus-02-15": "Qwen 3.5 Plus",
    "deepseek-chat": "DeepSeek V3.2",
    "kimi-k2.5": "Kimi K2.5",
    "kimi-k2-turbo-preview": "Kimi K2 Turbo",
    "moonshotai/kimi-k2.5": "Kimi K2.5",
    "baidu/ernie-4.5-300b-a47b": "ERNIE 4.5 300B",
    "baidu/ernie-4.5-21b-a3b": "ERNIE 4.5",
    "bytedance-seed/seed-1.6": "ByteDance Seed 1.6",
    "bytedance-seed/seed-2.0-lite": "ByteDance Seed 2.0",
    "minimax/minimax-m2.1": "MiniMax M2.1",
    "minimax/minimax-m2.5": "MiniMax M2.5",
}


def shorten_model_name(model_name: str) -> str:
    if model_name in _MODEL_SHORT_NAMES:
        return _MODEL_SHORT_NAMES[model_name]
    parts = model_name.split("/")
    return parts[-1].split(":")[0].title() if parts else model_name


_MODEL_SHORT_NAMES: dict[str, str] = {
    "qwen2.5:7b-instruct-q4_0": "Qwen 7B",
    "qwen/qwen-2.5-72b-instruct": "Qwen 72B",
    "qwen/qwen3.5-plus-02-15": "Qwen 3.5 Plus",
    "deepseek-chat": "DeepSeek V3.2",
    "kimi-k2.5": "Kimi K2.5",
    "kimi-k2-turbo-preview": "Kimi K2 Turbo",
    "moonshotai/kimi-k2.5": "Kimi K2.5",
    "baidu/ernie-4.5-300b-a47b": "ERNIE 4.5 300B",
    "baidu/ernie-4.5-21b-a3b": "ERNIE 4.5",
    "bytedance-seed/seed-1.6": "Seed 1.6",
    "bytedance-seed/seed-2.0-lite": "Seed 2.0",
    "minimax/minimax-m2.1": "MiniMax M2.1",
    "minimax/minimax-m2.5": "MiniMax M2.5",
}


def shorten_model_name(model_name: str) -> str:
    if model_name in _MODEL_SHORT_NAMES:
        return _MODEL_SHORT_NAMES[model_name]
    parts = model_name.split("/")
    return parts[-1].split(":")[0].title() if parts else model_name
def render_vertical_selector() -> tuple[str, int] | None:
    verticals = fetch_verticals()
    if not verticals:
        st.warning("No verticals found. Please create a tracking job first.")
        return None

    vertical_options = {v["name"]: v["id"] for v in verticals}
    selected_name = st.selectbox("Select Vertical", list(vertical_options.keys()))
    return selected_name, vertical_options[selected_name]
