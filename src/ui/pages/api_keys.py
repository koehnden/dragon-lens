import httpx
import streamlit as st

from src.config import settings
from src.models.domain import LLMProvider


def show():
    st.title("🔑 API Key Management")
    st.write("Manage API keys for remote LLM providers (DeepSeek, Kimi)")

    st.markdown("---")

    # Check if API keys are available
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/api-keys",
            timeout=10.0,
        )
        if response.status_code == 200:
            api_keys = response.json()
        else:
            api_keys = []
    except Exception:
        api_keys = []
        st.warning("⚠️ Could not connect to API. Make sure the FastAPI server is running.")

    st.header("Add New API Key")

    remote_providers = [p.value for p in LLMProvider if p != LLMProvider.QWEN]

    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "Provider",
            remote_providers,
            help="Select the LLM provider",
        )

    with col2:
        api_key = st.text_input(
            "API Key",
            type="password",
            help=f"Enter your {provider} API key",
        )

    if st.button("💾 Save API Key", type="primary"):
        if not api_key:
            st.error("❌ Please enter an API key")
            return

        payload = {
            "provider": provider,
            "api_key": api_key,
        }

        try:
            with st.spinner("Saving API key..."):
                response = httpx.post(
                    f"http://localhost:{settings.api_port}/api/v1/api-keys",
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                st.success("✅ API key saved successfully!")
                st.rerun()
        except httpx.HTTPError as e:
            if hasattr(e, "response") and e.response:
                if e.response.status_code == 400:
                    error_data = e.response.json()
                    st.error(f"❌ {error_data.get('detail', 'Error saving API key')}")
                else:
                    st.error(f"❌ Error saving API key: {e.response.text}")
            else:
                st.error(f"❌ Error saving API key: {e}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")

    st.markdown("---")
    st.header("Existing API Keys")

    if not api_keys:
        st.info("ℹ️ No API keys configured yet.")
    else:
        for key in api_keys:
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown(f"**Provider:** `{key['provider']}`")
                    st.markdown(f"**Status:** {'✅ Active' if key['is_active'] else '❌ Inactive'}")
                    st.markdown(f"**Created:** {key['created_at']}")
                with col2:
                    if st.button("Toggle Active", key=f"toggle_{key['id']}"):
                        try:
                            update_payload = {
                                "is_active": not key["is_active"],
                            }
                            response = httpx.put(
                                f"http://localhost:{settings.api_port}/api/v1/api-keys/{key['id']}",
                                json=update_payload,
                                timeout=30.0,
                            )
                            response.raise_for_status()
                            st.success("✅ API key updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error updating API key: {e}")
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{key['id']}"):
                        try:
                            response = httpx.delete(
                                f"http://localhost:{settings.api_port}/api/v1/api-keys/{key['id']}",
                                timeout=30.0,
                            )
                            response.raise_for_status()
                            st.success("✅ API key deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error deleting API key: {e}")

    st.markdown("---")
    st.header("Provider Information")

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
        
        **Models:**
        - `moonshot-v1-8k`: Standard model with 8K context
        - `moonshot-v1-32k`: Extended context model (32K)
        - `moonshot-v1-128k`: Long context model (128K)
        
        **Note:** Kimi integration is now available in V1!
        """)

    st.markdown("---")
    st.info("ℹ️ API keys are encrypted before storage and never logged or displayed in plaintext.")
