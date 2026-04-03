import httpx
import streamlit as st

from ui.api import api_url

REMOTE_PROVIDERS = ["deepseek", "kimi", "openrouter"]


def _fetch_api_keys() -> list[dict]:
    try:
        response = httpx.get(
            api_url("/api/v1/api-keys"),
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        st.warning("Could not connect to API. Make sure the FastAPI server is running.")
    return []


def _render_add_key_form() -> None:

    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "Provider",
            REMOTE_PROVIDERS,
            help="Select the LLM provider",
        )
    with col2:
        api_key = st.text_input(
            "API Key",
            type="password",
            help=f"Enter your {provider} API key",
        )

    if st.button("Save API Key", type="primary"):
        if not api_key:
            st.error("Please enter an API key")
            return
        try:
            with st.spinner("Saving API key..."):
                response = httpx.post(
                    api_url("/api/v1/api-keys"),
                    json={"provider": provider, "api_key": api_key},
                    timeout=30.0,
                )
                response.raise_for_status()
                st.success("API key saved successfully!")
                st.rerun()
        except httpx.HTTPError as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 400:
                error_data = e.response.json()
                st.error(error_data.get("detail", "Error saving API key"))
            else:
                st.error(f"Error saving API key: {e}")


def _render_existing_keys(api_keys: list[dict]) -> None:
    if not api_keys:
        st.info("No API keys configured yet.")
        return

    for key in api_keys:
        with st.container(border=True):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(f"**Provider:** `{key['provider']}`")
                status = "Active" if key["is_active"] else "Inactive"
                st.markdown(f"**Status:** {status}")
                st.markdown(f"**Created:** {key['created_at']}")
            with col2:
                if st.button("Toggle Active", key=f"toggle_{key['id']}"):
                    try:
                        response = httpx.put(
                            api_url(f"/api/v1/api-keys/{key['id']}"),
                            json={"is_active": not key["is_active"]},
                            timeout=30.0,
                        )
                        response.raise_for_status()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating API key: {e}")
            with col3:
                if st.button("Delete", key=f"delete_{key['id']}"):
                    try:
                        response = httpx.delete(
                            api_url(f"/api/v1/api-keys/{key['id']}"),
                            timeout=30.0,
                        )
                        response.raise_for_status()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting API key: {e}")


def _render_provider_info() -> None:
    with st.expander("DeepSeek API"):
        st.markdown("""
        **Getting an API Key:**
        1. Visit [DeepSeek Platform](https://platform.deepseek.com/)
        2. Sign up or log in
        3. Navigate to API Keys section
        4. Create a new API key

        **Pricing:**
        - Input (cache miss): $0.28 per 1M tokens
        - Output: $0.42 per 1M tokens

        **Models:**
        - `deepseek-chat`: Current stable chat ID for DeepSeek V3.2
        - `deepseek-reasoner`: Current stable reasoning ID for DeepSeek V3.2
        """)

    with st.expander("Kimi API (Moonshot AI)"):
        st.markdown("""
        **Getting an API Key:**
        1. Visit [Moonshot AI Platform](https://platform.moonshot.cn/)
        2. Sign up or log in
        3. Navigate to API Keys section
        4. Create a new API key

        **Recommended Model:**
        - `kimi-k2.5`: Current recommended Moonshot model for visibility runs

        **Legacy Models Still Supported:**
        - `moonshot-v1-8k`: $0.012 (input & output)
        - `moonshot-v1-32k`: $0.024 (input & output)
        - `moonshot-v1-128k`: $0.06 (input & output)

        **OpenRouter Equivalent:**
        - `moonshotai/kimi-k2.5`

        **Note:** Older Moonshot v1 and K2 preview IDs remain available for backward compatibility.
        """)

    with st.expander("OpenRouter API"):
        st.markdown("""
        **Getting an API Key:**
        1. Visit [OpenRouter](https://openrouter.ai/)
        2. Sign up or log in
        3. Navigate to API Keys
        4. Create a new API key

        **Models:**
        - `bytedance-seed/seed-2.0-lite`
        - `qwen/qwen3.5-plus-02-15`
        - `baidu/ernie-4.5-21b-a3b`
        - `minimax/minimax-m2.5`
        - `moonshotai/kimi-k2.5`
        - Any other OpenRouter model ID

        **Pricing:** Not available yet for OpenRouter runs in DragonLens.
        """)

    st.info("API keys are encrypted before storage and never logged or displayed in plaintext.")


def show() -> None:
    st.title("Settings")

    st.header("API Keys")
    st.write("Manage API keys for remote LLM providers (DeepSeek, Kimi, OpenRouter)")

    api_keys = _fetch_api_keys()

    _render_add_key_form()
    st.markdown("---")
    _render_existing_keys(api_keys)
    st.markdown("---")
    st.header("Provider Information")
    _render_provider_info()
