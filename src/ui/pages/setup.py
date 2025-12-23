import json

import httpx
import streamlit as st

from config import settings
from ui.prompt_parser import parse_prompt_entries


def show():
    st.title("🐉 DragonLens - Brand Visibility Tracker")
    st.write("Track how Chinese LLMs talk about your brand")

    st.markdown("---")

    st.header("1. Vertical Information")
    vertical_name = st.text_input(
        "Vertical Name",
        placeholder="e.g., SUV Cars, Smartphones, Coffee Brands",
        help="The industry or category you want to track",
    )
    vertical_description = st.text_area(
        "Description (optional)",
        placeholder="Brief description of this vertical",
    )

    st.header("2. Primary Brand")
    st.write("Track a single primary brand and let the system discover competitors automatically.")

    brand_name = st.text_input(
        "Brand Display Name",
        key="brand_name_primary",
        placeholder="e.g., 大众",
    )

    col1, col2 = st.columns(2)
    with col1:
        zh_aliases = st.text_area(
            "Chinese Aliases (one per line)",
            key="brand_zh_primary",
            placeholder="上汽大众\n一汽大众",
            help="Chinese names and variations for this brand",
        )
    with col2:
        en_aliases = st.text_area(
            "English Aliases (one per line)",
            key="brand_en_primary",
            placeholder="Volkswagen\nVW",
            help="English names and variations for this brand",
        )

    zh_list = [a.strip() for a in zh_aliases.split("\n") if a.strip()]
    en_list = [a.strip() for a in en_aliases.split("\n") if a.strip()]

    brands = []
    if brand_name:
        brands.append(
            {
                "display_name": brand_name,
                "aliases": {
                    "zh": zh_list,
                    "en": en_list,
                },
            }
        )

    st.header("3. Prompts")
    st.write("Paste prompts separated by new lines to add multiple at once.")

    prompt_language = st.radio(
        "Prompt Language",
        ["Chinese (中文)", "English"],
        key="prompt_language",
        horizontal=True,
    )

    prompts_text = st.text_area(
        "Prompts (one per line)",
        key="prompts_text",
        placeholder="推荐几款值得购买的SUV\n分享几款智能纯电车型\n比亚迪有哪些热门车型",
        height=200,
    )

    prompt_language_code = "zh" if prompt_language == "Chinese (中文)" else "en"
    prompts = parse_prompt_entries(prompts_text, prompt_language_code)

    st.header("4. LLM Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "LLM Provider",
            ["qwen", "deepseek", "kimi"],
            help="Choose which Chinese LLM provider to use",
        )
    
    with col2:
        if provider == "qwen":
            model_name = st.selectbox(
                "Qwen Model",
                ["qwen2.5:7b-instruct-q4_0", "qwen2.5:14b-instruct-q4_0", "qwen2.5:32b-instruct-q4_0"],
                help="Select specific Qwen model via Ollama",
            )
            st.info("✅ Qwen runs locally via Ollama (no API key needed)")
        elif provider == "deepseek":
            model_name = st.selectbox(
                "DeepSeek Model",
                ["deepseek-chat", "deepseek-reasoner"],
                help="Select DeepSeek model variant",
            )
            st.warning("⚠️ DeepSeek requires API key (configure in API Keys page)")
        elif provider == "kimi":
            model_name = st.selectbox(
                "Kimi Model",
                ["kimi2"],
                help="Select Kimi model variant",
            )
            st.warning("⚠️ Kimi requires API key (configure in API Keys page)")

    st.markdown("---")
    if st.button("🚀 Start Tracking", type="primary", use_container_width=True):
        if not vertical_name:
            st.error("❌ Please enter a vertical name")
            return

        if not brands:
            st.error("❌ Please add at least one brand")
            return

        if not prompts:
            st.error("❌ Please add at least one prompt")
            return

        payload = {
            "vertical_name": vertical_name,
            "vertical_description": vertical_description or None,
            "brands": brands,
            "prompts": prompts,
            "provider": provider,
            "model_name": model_name,
        }

        try:
            with st.spinner("Creating tracking job..."):
                response = httpx.post(
                    f"http://localhost:{settings.api_port}/api/v1/tracking/jobs",
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

            st.success(f"✅ {result['message']}")
            st.info(f"Run ID: {result['run_id']} | Vertical ID: {result['vertical_id']}")
            st.balloons()

        except httpx.HTTPError as e:
            st.error(f"❌ Error creating tracking job: {e}")
            if hasattr(e, "response") and e.response:
                st.error(f"Details: {e.response.text}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")

    with st.expander("🔍 Debug: View API Payload"):
        payload = {
            "vertical_name": vertical_name,
            "vertical_description": vertical_description or None,
            "brands": brands,
            "prompts": prompts,
            "provider": provider,
            "model_name": model_name,
        }
        st.json(payload)
