import json

import httpx
import streamlit as st

from src.config import settings


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

    st.header("2. Brands to Track")
    st.write("Add the brands you want to track, including your own brand and competitors.")

    num_brands = st.number_input("Number of brands", min_value=1, max_value=20, value=3)

    brands = []
    for i in range(num_brands):
        with st.expander(f"Brand {i + 1}", expanded=(i == 0)):
            brand_name = st.text_input(
                "Brand Display Name",
                key=f"brand_name_{i}",
                placeholder="e.g., Tesla Model Y",
            )

            col1, col2 = st.columns(2)
            with col1:
                zh_aliases = st.text_area(
                    "Chinese Aliases (one per line)",
                    key=f"brand_zh_{i}",
                    placeholder="特斯拉Model Y\n特斯拉Y\nTesla Y",
                    help="Chinese names and variations for this brand",
                )
            with col2:
                en_aliases = st.text_area(
                    "English Aliases (one per line)",
                    key=f"brand_en_{i}",
                    placeholder="Tesla Model Y\nModel Y\nTesla Y",
                    help="English names and variations for this brand",
                )

            zh_list = [a.strip() for a in zh_aliases.split("\n") if a.strip()]
            en_list = [a.strip() for a in en_aliases.split("\n") if a.strip()]

            if brand_name:
                brands.append({
                    "display_name": brand_name,
                    "aliases": {
                        "zh": zh_list,
                        "en": en_list,
                    }
                })

    st.header("3. Prompts")
    st.write("Add prompts to ask the LLMs. You can use English or Chinese.")

    num_prompts = st.number_input("Number of prompts", min_value=1, max_value=20, value=2)

    prompts = []
    for i in range(num_prompts):
        with st.expander(f"Prompt {i + 1}", expanded=(i == 0)):
            lang = st.radio(
                "Language",
                ["Chinese (中文)", "English"],
                key=f"prompt_lang_{i}",
                horizontal=True,
            )

            prompt_text = st.text_area(
                "Prompt Text",
                key=f"prompt_text_{i}",
                placeholder="e.g., 推荐几款值得购买的SUV (Recommend some SUVs worth buying)",
                height=100,
            )

            if prompt_text:
                if lang == "Chinese (中文)":
                    prompts.append({
                        "text_zh": prompt_text,
                        "text_en": None,
                        "language_original": "zh",
                    })
                else:
                    prompts.append({
                        "text_en": prompt_text,
                        "text_zh": None,
                        "language_original": "en",
                    })

    st.header("4. Model Selection")
    model_name = st.selectbox(
        "Select LLM Model",
        ["qwen", "deepseek", "kimi"],
        help="Choose which Chinese LLM to query",
    )

    if model_name == "qwen":
        st.info("✅ Qwen runs locally via Ollama (no API key needed)")
    elif model_name == "deepseek":
        st.warning("⚠️ DeepSeek requires API key in .env file")
    elif model_name == "kimi":
        st.warning("⚠️ Kimi requires API key in .env file (V2 feature)")

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
            "model_name": model_name,
        }
        st.json(payload)
