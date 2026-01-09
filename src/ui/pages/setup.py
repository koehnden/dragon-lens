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

    st.header("3b. Comparison Prompts (Optional)")
    comparison_enabled = st.checkbox(
        "Enable comparison prompts (sentiment-only, runs after the main job)",
        value=False,
    )

    comparison_competitor_brands = []
    comparison_prompts = []
    comparison_target_count = 20
    comparison_min_per_competitor = 2
    comparison_autogenerate_missing = True

    if comparison_enabled:
        competitor_text = st.text_area(
            "Competitor Brands (one per line, optional)",
            key="comparison_competitors",
            placeholder="Salomon\nMerrell",
            height=120,
        )
        comparison_competitor_brands = [c.strip() for c in competitor_text.splitlines() if c.strip()]

        comparison_prompt_language = st.radio(
            "Comparison Prompt Language (for your examples)",
            ["Chinese (中文)", "English"],
            key="comparison_prompt_language",
            horizontal=True,
        )
        comparison_prompts_text = st.text_area(
            "Comparison Prompts (one per line, optional)",
            key="comparison_prompts_text",
            placeholder="Between Brand A and Brand B, which would you recommend and why?\n对比品牌A和品牌B的优缺点，并给出不推荐的场景。",
            height=160,
        )
        comparison_prompt_language_code = "zh" if comparison_prompt_language == "Chinese (中文)" else "en"
        comparison_prompts = parse_prompt_entries(comparison_prompts_text, comparison_prompt_language_code)

        col1, col2, col3 = st.columns(3)
        with col1:
            comparison_target_count = st.number_input("Target Comparison Prompts", min_value=1, max_value=500, value=20, step=1)
        with col2:
            comparison_min_per_competitor = st.number_input("Min Prompts per Competitor", min_value=0, max_value=50, value=2, step=1)
        with col3:
            comparison_autogenerate_missing = st.checkbox("Auto-generate missing prompts", value=True)

    st.header("4. LLM Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox(
            "LLM Provider",
            ["qwen", "deepseek", "kimi", "openrouter"],
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
            st.warning("⚠️ DeepSeek uses vendor API key first, then OpenRouter if needed")
        elif provider == "kimi":
            model_name = st.selectbox(
                "Kimi Model",
                ["kimi-k2-turbo-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
                help="Select Kimi model variant (Moonshot API)",
            )
            st.info("ℹ️ Kimi K2 Turbo is the recommended K2 variant for the Moonshot API.")
        elif provider == "openrouter":
            preset_models = [
                "moonshotai/kimi-k2-0905",
                "baidu/ernie-4.5-300b-a47b",
                "bytedance-seed/seed-1.6",
                "bytedance-seed/seed-1.6-flash",
                "qwen/qwen-2.5-72b-instruct",
                "minimax/minimax-m2.1",
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
            "comparison_enabled": comparison_enabled,
            "comparison_competitor_brands": comparison_competitor_brands,
            "comparison_prompts": comparison_prompts,
            "comparison_target_count": int(comparison_target_count),
            "comparison_min_prompts_per_competitor": int(comparison_min_per_competitor),
            "comparison_autogenerate_missing": comparison_autogenerate_missing,
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
            "comparison_enabled": comparison_enabled,
            "comparison_competitor_brands": comparison_competitor_brands,
            "comparison_prompts": comparison_prompts,
            "comparison_target_count": int(comparison_target_count),
            "comparison_min_prompts_per_competitor": int(comparison_min_per_competitor),
            "comparison_autogenerate_missing": comparison_autogenerate_missing,
        }
        st.json(payload)
