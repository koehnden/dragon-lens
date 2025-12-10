import httpx
import pandas as pd
import streamlit as st

from src.config import settings


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

            st.markdown("### Brand Mention Overview")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Brands", len(df))

            with col2:
                avg_mention = df["mention_rate"].mean() * 100
                st.metric("Avg Mention Rate", f"{avg_mention:.1f}%")

            with col3:
                mentioned_brands = (df["mention_rate"] > 0).sum()
                st.metric("Brands Mentioned", mentioned_brands)

            st.markdown("### Mention Rates")
            display_df = df.copy()
            display_df["mention_rate"] = (display_df["mention_rate"] * 100).round(1).astype(str) + "%"
            display_df["avg_rank"] = display_df["avg_rank"].fillna("-")

            st.dataframe(
                display_df[[
                    "brand_name",
                    "mention_rate",
                    "avg_rank",
                    "sentiment_positive",
                    "sentiment_neutral",
                    "sentiment_negative",
                ]],
                use_container_width=True,
                hide_index=True,
            )

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Mention Rate by Brand")
                chart_data = df[["brand_name", "mention_rate"]].copy()
                chart_data["mention_rate"] = chart_data["mention_rate"] * 100
                st.bar_chart(chart_data.set_index("brand_name"))

            with col2:
                st.markdown("### Sentiment Distribution")
                sentiment_data = df[["brand_name", "sentiment_positive", "sentiment_neutral", "sentiment_negative"]].copy()
                sentiment_data = sentiment_data.set_index("brand_name")
                st.bar_chart(sentiment_data)

            rank_df = df[df["avg_rank"].notna()].copy()
            if not rank_df.empty:
                st.markdown("### Average Rank")
                st.caption("Lower is better (1 = first mention)")
                rank_chart = rank_df[["brand_name", "avg_rank"]].set_index("brand_name")
                st.bar_chart(rank_chart)

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
