import httpx
import streamlit as st

from config import settings


def api_url(path: str) -> str:
    return f"http://localhost:{settings.api_port}{path}"


def fetch_json(path: str, params: dict | None = None, timeout: float = 30.0) -> dict | list | None:
    try:
        response = httpx.get(api_url(path), params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Request failed: {exc}")
        return None


def fetch_verticals() -> list[dict]:
    return fetch_json("/api/v1/verticals", timeout=10.0) or []


def fetch_available_models(vertical_id: int) -> list[str]:
    return fetch_json(f"/api/v1/verticals/{vertical_id}/models", timeout=10.0) or []


def fetch_user_brands(vertical_id: int) -> list[str]:
    brands = fetch_json(
        f"/api/v1/verticals/{vertical_id}/brands",
        params={"user_input_only": True},
        timeout=10.0,
    )
    if not brands:
        return []
    return [b["display_name"] for b in brands]


def render_vertical_selector() -> tuple[str, int] | None:
    verticals = fetch_verticals()
    if not verticals:
        st.warning("No verticals found. Please create a tracking job first.")
        return None

    vertical_options = {v["name"]: v["id"] for v in verticals}
    selected_name = st.selectbox("Select Vertical", list(vertical_options.keys()))
    return selected_name, vertical_options[selected_name]
