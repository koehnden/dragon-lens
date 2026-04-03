import httpx
import streamlit as st

from ui.prompt_parser import parse_prompt_entries
from ui.api import api_url


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

    st.info("Comparison prompts run automatically after the main job (20 product-vs-product prompts, Chinese only).")

    st.header("4. LLM Configuration")
    st.caption(
        "Local Qwen remains available for internal testing and extraction flows, "
        "but normal visibility runs use the current remote Chinese model lineup."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "LLM Provider",
            ["deepseek", "kimi", "openrouter"],
            help="Choose which Chinese LLM provider to use",
        )
    
    with col2:
        if provider == "deepseek":
            model_name = st.selectbox(
                "DeepSeek Model",
                ["deepseek-chat", "deepseek-reasoner"],
                help="Select DeepSeek model variant",
            )
            st.warning("⚠️ DeepSeek uses vendor API key first, then OpenRouter if needed")
        elif provider == "kimi":
            model_name = st.selectbox(
                "Kimi Model",
                ["kimi-k2.5"],
                help="Select Kimi model variant (Moonshot API)",
            )
            st.info("ℹ️ Kimi K2.5 is the recommended Moonshot model for visibility runs.")
        elif provider == "openrouter":
            preset_models = [
                "bytedance-seed/seed-2.0-lite",
                "qwen/qwen3.5-plus-02-15",
                "baidu/ernie-4.5-21b-a3b",
                "minimax/minimax-m2.5",
                "moonshotai/kimi-k2.5",
                "Custom model ID",
            ]
            selected_model = st.selectbox(
                "OpenRouter Model",
                preset_models,
                help="Pick a preset or enter a custom OpenRouter model ID",
            )
            if selected_model == "Custom model ID":
                model_name = st.text_input(
                    "Custom OpenRouter Model ID",
                    placeholder="provider/model",
                )
            else:
                model_name = selected_model
            st.warning("⚠️ OpenRouter requires an API key. Pricing estimates are not available yet.")

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
        if provider == "openrouter" and not model_name:
            st.error("❌ Please enter an OpenRouter model ID")
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
                    api_url("/api/v1/tracking/jobs"),
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
