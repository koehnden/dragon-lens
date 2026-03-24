import httpx
import streamlit as st

from config import settings

REMOTE_PROVIDERS = ["deepseek", "kimi", "openrouter"]


def _fetch_api_keys() -> list[dict]:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/api-keys",
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
                    f"http://localhost:{settings.api_port}/api/v1/api-keys",
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
                            f"http://localhost:{settings.api_port}/api/v1/api-keys/{key['id']}",
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
                            f"http://localhost:{settings.api_port}/api/v1/api-keys/{key['id']}",
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
        - Input: $0.14 per 1M tokens
        - Output: $0.28 per 1M tokens

        **Models:**
        - `deepseek-chat`: General purpose chat model
        - `deepseek-reasoner`: Enhanced reasoning capabilities
        """)

    with st.expander("Kimi API (Moonshot AI)"):
        st.markdown("""
        **Getting an API Key:**
        1. Visit [Moonshot AI Platform](https://platform.moonshot.cn/)
        2. Sign up or log in
        3. Navigate to API Keys section
        4. Create a new API key

        **Pricing (per 1K tokens):**
        - `moonshot-v1-8k`: $0.012 (input & output)
        - `moonshot-v1-32k`: $0.024 (input & output)
        - `moonshot-v1-128k`: $0.06 (input & output)

        **Models (direct Moonshot API):**
        - `kimi-k2-turbo-preview`: Kimi K2 Turbo (recommended for complex prompts)
        - `moonshot-v1-8k`: Standard model with 8K context
        - `moonshot-v1-32k`: Extended context model (32K)
        - `moonshot-v1-128k`: Long context model (128K)

        **Note:** Use `kimi-k2-turbo-preview` for best results with K2.
        Also available via OpenRouter as `moonshotai/kimi-k2-0905`.
        """)

    with st.expander("OpenRouter API"):
        st.markdown("""
        **Getting an API Key:**
        1. Visit [OpenRouter](https://openrouter.ai/)
        2. Sign up or log in
        3. Navigate to API Keys
        4. Create a new API key

        **Models:**
        - `moonshotai/kimi-k2-0905` (Kimi K2 - only available via OpenRouter)
        - `baidu/ernie-4.5-300b-a47b`
        - `bytedance-seed/seed-1.6`
        - `bytedance-seed/seed-1.6-flash`
        - `qwen/qwen-2.5-72b-instruct`
        - `minimax/minimax-m2.1`
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
