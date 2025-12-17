import httpx
import pandas as pd
import streamlit as st

from config import settings


def show():
    st.title("📊 Brand Visibility Results")

    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/verticals",
            timeout=10.0,
        )
        response.raise_for_status()
        verticals = response.json()

        if not verticals:
            st.warning("⚠️ No verticals found. Please create a tracking job first.")
            return

    except httpx.HTTPError as e:
        st.error(f"❌ Error fetching verticals: {e}")
        return

    col1, col2 = st.columns(2)

    with col1:
        vertical_options = {v["name"]: v["id"] for v in verticals}
        selected_vertical_name = st.selectbox("Select Vertical", list(vertical_options.keys()))
        selected_vertical_id = vertical_options[selected_vertical_name]

    with col2:
        model_name = st.selectbox("Select Model", ["qwen", "deepseek", "kimi"])

    if st.button("🔍 Load Metrics", type="primary"):
        try:
            with st.spinner("Fetching metrics..."):
                response = httpx.get(
                    f"http://localhost:{settings.api_port}/api/v1/metrics/latest",
                    params={
                        "vertical_id": selected_vertical_id,
                        "model_name": model_name,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                metrics = response.json()

            st.subheader(f"Latest Metrics: {metrics['vertical_name']} ({metrics['model_name']})")
            st.caption(f"Data from: {metrics['date']}")

            if not metrics["brands"]:
                st.info("ℹ️ No brand metrics available yet. The tracking job may still be processing.")
                return

            df = pd.DataFrame(metrics["brands"])

            brands_only_df = df.copy()
            if "entity_type" in brands_only_df.columns:
                brands_only_df = brands_only_df[brands_only_df["entity_type"] == "brand"]

            st.markdown("### Brand Mention Overview")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Brands", len(brands_only_df))

            with col2:
                if len(brands_only_df) > 0:
                    avg_mention = brands_only_df["mention_rate"].mean() * 100
                else:
                    avg_mention = 0
                st.metric("Avg Mention Rate", f"{avg_mention:.1f}%")

            with col3:
                mentioned_brands = (brands_only_df["mention_rate"] > 0).sum()
                st.metric("Brands Mentioned", mentioned_brands)

            st.markdown("### Brands Overview")

            brands_df = df.copy()
            if "entity_type" in brands_df.columns:
                brands_df = brands_df[brands_df["entity_type"] == "brand"]

            brands_df = brands_df.sort_values("dragon_lens_visibility", ascending=False)

            display_df = brands_df.copy()
            display_df["Mention Rate"] = (display_df["mention_rate"] * 100).round(1).astype(str) + "%"
            display_df["Share of Voice"] = (display_df["share_of_voice"] * 100).round(1).astype(str) + "%"
            display_df["Top Spot Share"] = (display_df["top_spot_share"] * 100).round(1).astype(str) + "%"
            display_df["Sentiment Index"] = display_df["sentiment_index"].round(3)
            display_df["DVS"] = display_df["dragon_lens_visibility"].round(3)

            st.dataframe(
                display_df[[
                    "brand_name",
                    "Mention Rate",
                    "Share of Voice",
                    "Top Spot Share",
                    "Sentiment Index",
                    "DVS",
                ]].rename(columns={"brand_name": "Brand"}),
                use_container_width=True,
                hide_index=True,
            )

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Mention Rate by Brand")
                chart_data = brands_df[["brand_name", "mention_rate"]].copy()
                chart_data["mention_rate"] = chart_data["mention_rate"] * 100
                st.bar_chart(chart_data.set_index("brand_name"))

            with col2:
                st.markdown("### Share of Voice")
                sov_data = brands_df[["brand_name", "share_of_voice"]].copy()
                sov_data["share_of_voice"] = sov_data["share_of_voice"] * 100
                st.bar_chart(sov_data.set_index("brand_name"))

            st.markdown("---")
            st.markdown("## 🎯 Visibility Metrics")
            st.caption("Comprehensive brand visibility metrics from the latest run")

            try:
                metrics_response = httpx.get(
                    f"http://localhost:{settings.api_port}/api/v1/metrics/run/{latest_run_id}",
                    timeout=10.0,
                )
                metrics_response.raise_for_status()
                run_metrics = metrics_response.json()

                if run_metrics["metrics"]:
                    metrics_df = pd.DataFrame(run_metrics["metrics"])

                    user_brands_df = metrics_df[metrics_df["is_user_input"] == True].copy()
                    discovered_brands_df = metrics_df[metrics_df["is_user_input"] == False].copy()

                    if not user_brands_df.empty:
                        st.markdown("#### Your Brands (User Input)")
                        display_user_df = user_brands_df.copy()
                        display_user_df["Mention Rate"] = (display_user_df["mention_rate"] * 100).round(1).astype(str) + "%"
                        display_user_df["Share of Voice"] = (display_user_df["share_of_voice"] * 100).round(1).astype(str) + "%"
                        display_user_df["Top Spot Share"] = (display_user_df["top_spot_share"] * 100).round(1).astype(str) + "%"
                        display_user_df["Sentiment Index"] = display_user_df["sentiment_index"].round(3)
                        display_user_df["Dragon Lens Visibility"] = display_user_df["dragon_lens_visibility"].round(3)

                        st.dataframe(
                            display_user_df[[
                                "brand_name",
                                "Mention Rate",
                                "Share of Voice",
                                "Top Spot Share",
                                "Sentiment Index",
                                "Dragon Lens Visibility",
                            ]].rename(columns={"brand_name": "Brand"}),
                            use_container_width=True,
                            hide_index=True,
                        )

                    if not discovered_brands_df.empty:
                        st.markdown("#### Competitor Brands (Discovered in Responses)")
                        display_discovered_df = discovered_brands_df.copy()
                        display_discovered_df["Mention Rate"] = (display_discovered_df["mention_rate"] * 100).round(1).astype(str) + "%"
                        display_discovered_df["Share of Voice"] = (display_discovered_df["share_of_voice"] * 100).round(1).astype(str) + "%"
                        display_discovered_df["Top Spot Share"] = (display_discovered_df["top_spot_share"] * 100).round(1).astype(str) + "%"
                        display_discovered_df["Sentiment Index"] = display_discovered_df["sentiment_index"].round(3)
                        display_discovered_df["Dragon Lens Visibility"] = display_discovered_df["dragon_lens_visibility"].round(3)

                        st.dataframe(
                            display_discovered_df[[
                                "brand_name",
                                "Mention Rate",
                                "Share of Voice",
                                "Top Spot Share",
                                "Sentiment Index",
                                "Dragon Lens Visibility",
                            ]].rename(columns={"brand_name": "Brand"}),
                            use_container_width=True,
                            hide_index=True,
                        )

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("### Dragon Lens Visibility")
                        dvs_chart = metrics_df[["brand_name", "dragon_lens_visibility"]].copy()
                        dvs_chart = dvs_chart.set_index("brand_name")
                        st.bar_chart(dvs_chart)

                    with col2:
                        st.markdown("### Share of Voice")
                        sov_chart = metrics_df[["brand_name", "share_of_voice"]].copy()
                        sov_chart["share_of_voice"] = sov_chart["share_of_voice"] * 100
                        sov_chart = sov_chart.set_index("brand_name")
                        st.bar_chart(sov_chart)

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("### Mention Rate")
                        mention_chart = metrics_df[["brand_name", "mention_rate"]].copy()
                        mention_chart["mention_rate"] = mention_chart["mention_rate"] * 100
                        mention_chart = mention_chart.set_index("brand_name")
                        st.bar_chart(mention_chart)

                    with col2:
                        st.markdown("### Sentiment Index")
                        sent_chart = metrics_df[["brand_name", "sentiment_index"]].copy()
                        sent_chart = sent_chart.set_index("brand_name")
                        st.bar_chart(sent_chart)

                else:
                    st.info("ℹ️ No metrics available for this run yet.")

            except httpx.HTTPError as e:
                st.warning(f"⚠️ Could not load visibility metrics: {e}")
            except Exception as e:
                st.error(f"❌ Error loading visibility metrics: {e}")

            st.markdown("---")
            st.markdown("## 🔍 Last Run Inspector")
            st.caption("View raw answers and extracted brand mentions from the most recent run")

            try:
                runs_response = httpx.get(
                    f"http://localhost:{settings.api_port}/api/v1/tracking/runs",
                    params={
                        "vertical_id": selected_vertical_id,
                        "model_name": model_name,
                        "limit": 1,
                    },
                    timeout=10.0,
                )
                runs_response.raise_for_status()
                runs = runs_response.json()

                if not runs:
                    st.info("ℹ️ No runs found for this vertical and model.")
                else:
                    latest_run_id = runs[0]["id"]
                    details_response = httpx.get(
                        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{latest_run_id}/details",
                        timeout=30.0,
                    )
                    details_response.raise_for_status()
                    run_details = details_response.json()

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Run ID", run_details["id"])
                    with col2:
                        st.metric("Status", run_details["status"])
                    with col3:
                        st.metric("Prompts Answered", len(run_details["answers"]))

                    if not run_details["answers"]:
                        st.info("ℹ️ No answers available for this run yet. The job may still be processing.")
                    else:
                        for i, answer in enumerate(run_details["answers"], 1):
                            with st.expander(f"📝 Prompt & Answer {i}", expanded=(i == 1)):
                                st.markdown("#### Prompt")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.markdown("**Chinese:**")
                                    st.write(answer.get("prompt_text_zh") or "_No Chinese prompt_")
                                with col2:
                                    st.markdown("**English:**")
                                    st.write(answer.get("prompt_text_en") or "_No English prompt_")

                                st.markdown("---")
                                st.markdown("#### LLM Answer")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.markdown("**Chinese Answer:**")
                                    st.text_area(
                                        "Chinese",
                                        answer["raw_answer_zh"],
                                        height=150,
                                        key=f"answer_zh_{i}",
                                        label_visibility="collapsed",
                                    )
                                with col2:
                                    st.markdown("**English Translation:**")
                                    st.text_area(
                                        "English",
                                        answer.get("raw_answer_en") or "_Translation not available_",
                                        height=150,
                                        key=f"answer_en_{i}",
                                        label_visibility="collapsed",
                                    )

                                st.markdown("---")
                                st.markdown("#### 🏷️ Brand Mentions Detected")

                                if not answer["mentions"]:
                                    st.info("No brand mentions detected in this answer.")
                                else:
                                    mentioned_brands = [m for m in answer["mentions"] if m["mentioned"]]
                                    if not mentioned_brands:
                                        st.info("No brands were mentioned in this answer.")
                                    else:
                                        for mention in mentioned_brands:
                                            sentiment_emoji = {
                                                "positive": "😊",
                                                "neutral": "😐",
                                                "negative": "😟",
                                            }.get(mention["sentiment"], "")

                                            rank_text = f"Rank #{mention['rank']}" if mention.get("rank") else "No rank"
                                            st.markdown(
                                                f"**{mention['brand_name']}** {sentiment_emoji} "
                                                f"| {mention['sentiment'].upper()} | {rank_text}"
                                            )

                                            if mention.get("evidence_snippets"):
                                                zh_snippets = mention["evidence_snippets"].get("zh", [])
                                                en_snippets = mention["evidence_snippets"].get("en", [])

                                                if zh_snippets or en_snippets:
                                                    col1, col2 = st.columns(2)
                                                    with col1:
                                                        if zh_snippets:
                                                            st.caption("Evidence (Chinese):")
                                                            for snippet in zh_snippets:
                                                                st.markdown(f"> {snippet}")
                                                    with col2:
                                                        if en_snippets:
                                                            st.caption("Evidence (English):")
                                                            for snippet in en_snippets:
                                                                st.markdown(f"> {snippet}")

                                            st.markdown("---")

            except httpx.HTTPError as e:
                st.error(f"❌ Error fetching run details: {e}")
                if hasattr(e, "response") and e.response:
                    st.error(f"Details: {e.response.text}")
            except Exception as e:
                st.error(f"❌ Unexpected error loading run inspector: {e}")

        except httpx.HTTPError as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 404:
                st.warning(f"⚠️ No data found for this vertical and model combination.")
                st.info("Make sure a tracking job has been run and completed.")
            else:
                st.error(f"❌ Error fetching metrics: {e}")
                if hasattr(e, "response") and e.response:
                    st.error(f"Details: {e.response.text}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
