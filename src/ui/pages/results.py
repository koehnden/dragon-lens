import httpx
import pandas as pd
import streamlit as st

from config import settings
from ui.components.charts import (
    render_metrics_comparison_bar,
    render_positioning_matrix,
    render_radar_chart,
    render_sentiment_breakdown,
    render_sov_bar_chart,
    render_sov_treemap,
)
from ui.components.insights import render_insights, render_opportunity_analysis


def _fetch_available_models(vertical_id: int) -> list[str]:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/models",
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []


def _fetch_metrics(vertical_id: int, model_name: str, view_mode: str) -> dict | None:
    endpoint = "/api/v1/metrics/latest"
    if view_mode == "Product":
        endpoint = "/api/v1/metrics/latest/products"

    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}{endpoint}",
            params={"vertical_id": vertical_id, "model_name": model_name},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _fetch_latest_completed_run(vertical_id: int, model_name: str) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/tracking/runs",
            params={"vertical_id": vertical_id, "model_name": model_name, "limit": 50},
            timeout=10.0,
        )
        response.raise_for_status()
        runs = response.json()
    except httpx.HTTPError:
        return None
    for run in runs:
        if run.get("status") == "completed":
            return run
    return None


def _fetch_run_brand_metrics(run_id: int) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/metrics/run/{run_id}",
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return {"brands": data.get("metrics") or []}
    except httpx.HTTPError:
        return None


def _fetch_run_product_metrics(run_id: int) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/metrics/run/{run_id}/products",
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _fetch_run_comparison(run_id: int, include_snippets: bool) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/metrics/run/{run_id}/comparison",
            params={
                "include_snippets": include_snippets,
                "limit_entities": 50,
                "limit_snippets": 3,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _fetch_run_comparison_summary(run_id: int, include_prompt_details: bool) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/metrics/run/{run_id}/comparison/summary",
            params={
                "include_prompt_details": include_prompt_details,
                "limit_prompts": 100,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _fetch_user_brands(vertical_id: int) -> list[str]:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/brands",
            params={"user_input_only": True},
            timeout=10.0,
        )
        response.raise_for_status()
        brands = response.json()
        return [b["display_name"] for b in brands]
    except httpx.HTTPError:
        return []


def _get_sentiment_label(sentiment_index: float) -> str:
    if sentiment_index > 0.3:
        return "Positive"
    elif sentiment_index < -0.3:
        return "Negative"
    return "Neutral"


def _render_comparison_tab(comparison: dict) -> None:
    st.markdown("### Brand & Product Comparison Sentiment")
    st.write(f"Primary brand: **{comparison.get('primary_brand_name', '')}**")

    messages = comparison.get("messages") or []
    if messages:
        with st.expander("Processing Messages"):
            for m in messages:
                st.write(f"{m.get('level')}: {m.get('message')}")

    brands = comparison.get("brands") or []
    products = comparison.get("products") or []

    if brands:
        st.markdown("#### Brand Comparison")
        st.dataframe(brands, use_container_width=True, hide_index=True)

    if products:
        st.markdown("#### Product Comparison")
        st.dataframe(products, use_container_width=True, hide_index=True)

    if not brands and not products:
        st.info("No comparison data available for this run.")


def _sentiment_table(rows: list[dict], label: str) -> None:
    if not rows:
        st.info(f"No {label} data available.")
        return
    df = pd.DataFrame(rows).copy()
    if "sentiment_index" in df.columns:
        df = df.sort_values("sentiment_index", ascending=False)
    cols = [c for c in ["entity_name", "entity_role", "sentiment_index", "positive_count", "neutral_count", "negative_count"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


def _render_prompt_outcome_details(rows: list[dict]) -> None:
    if not rows:
        st.info("No prompt details available.")
        return
    df = pd.DataFrame(rows).copy()
    cols = [
        "characteristic_en",
        "primary_product_name",
        "competitor_product_name",
        "winner_role",
        "winner_product_name",
        "loser_product_name",
    ]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    for r in rows:
        title = f"{r.get('characteristic_en', '')}: {r.get('primary_product_name', '')} vs {r.get('competitor_product_name', '')}"
        winner = r.get("winner_product_name") or r.get("winner_role") or ""
        with st.expander(f"{title} (winner: {winner})"):
            st.markdown("**Prompt (EN)**")
            st.write(r.get("prompt_en") or "")
            st.markdown("**Answer (EN)**")
            st.write(r.get("answer_en") or "")


def _render_comparison_summary_tab(run_id: int, summary: dict) -> None:
    st.markdown("### Winners & Losers (Comparison Prompts)")
    st.write(f"Primary brand: **{summary.get('primary_brand_name', '')}**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Brand Sentiment Index (Comparison)")
        _sentiment_table(summary.get("brands") or [], "brand")
    with col2:
        st.markdown("#### Product Sentiment Index (Comparison)")
        _sentiment_table(summary.get("products") or [], "product")
    st.markdown("#### Outcome Summary by Characteristic")
    characteristics = summary.get("characteristics") or []
    if not characteristics:
        st.info("No characteristic summary available.")
    else:
        df = pd.DataFrame(characteristics).copy()
        cols = [
            "characteristic_en",
            "total_prompts",
            "primary_wins",
            "competitor_wins",
            "ties",
            "unknown",
        ]
        cols = [c for c in cols if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    with st.expander("Prompt details (translated prompts and answers)", expanded=False):
        include_details = st.checkbox("Load prompt details", value=False, key=f"comparison_details_{run_id}")
        if include_details:
            details = _fetch_run_comparison_summary(run_id, include_prompt_details=True)
            if not details:
                st.info("Prompt details are not available yet.")
            else:
                _render_prompt_outcome_details(details.get("prompts") or [])


def _render_executive_scorecard(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    st.markdown("### Executive Scorecard")

    if user_brand and user_brand in df[name_col].values:
        user_data = df[df[name_col] == user_brand].iloc[0]
        user_rank = (df["dragon_lens_visibility"] > user_data["dragon_lens_visibility"]).sum() + 1
    else:
        user_data = df.nlargest(1, "dragon_lens_visibility").iloc[0]
        user_rank = 1
        user_brand = user_data[name_col]

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        dvs_score = user_data["dragon_lens_visibility"] * 100
        st.metric(
            "Visibility Score",
            f"{dvs_score:.0f}/100",
            help="Dragon Lens Visibility Score (0-100)",
        )

    with col2:
        sov = user_data["share_of_voice"] * 100
        st.metric(
            "Share of Voice",
            f"{sov:.1f}%",
            help="Percentage of all brand mentions",
        )

    with col3:
        mention = user_data["mention_rate"] * 100
        st.metric(
            "Mention Rate",
            f"{mention:.1f}%",
            help="Percentage of prompts mentioning your brand",
        )

    with col4:
        sentiment = user_data["sentiment_index"]
        sentiment_label = _get_sentiment_label(sentiment)
        st.metric(
            "Sentiment",
            sentiment_label,
            f"{sentiment:+.2f}",
            help="Overall sentiment index (-1 to +1)",
        )

    with col5:
        total_brands = len(df)
        st.metric(
            "Market Rank",
            f"#{user_rank} of {total_brands}",
            help="Your position among all brands by DVS",
        )

    st.caption(f"Showing metrics for: **{user_brand}**")


def _render_competitive_landscape_tab(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    col1, col2 = st.columns([2, 1])

    with col1:
        render_positioning_matrix(df, name_col, user_brand)

    with col2:
        render_sov_treemap(df, name_col)

    st.markdown("---")
    render_sov_bar_chart(df, name_col, user_brand)


def _render_performance_tab(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    col1, col2 = st.columns(2)

    with col1:
        brands_to_compare = []
        if user_brand and user_brand in df[name_col].values:
            brands_to_compare.append(user_brand)
            top_competitors = df[df[name_col] != user_brand].nlargest(2, "dragon_lens_visibility")[name_col].tolist()
            brands_to_compare.extend(top_competitors)
        else:
            brands_to_compare = df.nlargest(3, "dragon_lens_visibility")[name_col].tolist()

        render_radar_chart(df, name_col, brands_to_compare)

    with col2:
        render_sentiment_breakdown(df, name_col)

    st.markdown("---")
    render_metrics_comparison_bar(df, name_col)


def _render_opportunities_tab(df: pd.DataFrame, name_col: str, user_brand: str = None) -> None:
    col1, col2 = st.columns([1, 1])

    with col1:
        render_insights(df, name_col, user_brand)

    with col2:
        render_opportunity_analysis(df, name_col, user_brand)


def _render_data_tab(df: pd.DataFrame, name_col: str) -> None:
    st.markdown("### Detailed Data")

    display_df = df.copy()
    display_df = display_df.sort_values("dragon_lens_visibility", ascending=False)

    display_df["Visibility Score"] = (display_df["dragon_lens_visibility"] * 100).round(0).astype(int)
    display_df["Mention Rate"] = (display_df["mention_rate"] * 100).round(1).astype(str) + "%"
    display_df["Share of Voice"] = (display_df["share_of_voice"] * 100).round(1).astype(str) + "%"
    display_df["Top Spot Share"] = (display_df["top_spot_share"] * 100).round(1).astype(str) + "%"
    display_df["Sentiment Index"] = display_df["sentiment_index"].round(3)

    display_df["Rank"] = range(1, len(display_df) + 1)

    if name_col == "brand_name":
        columns = ["Rank", "brand_name", "Visibility Score", "Mention Rate", "Share of Voice", "Top Spot Share", "Sentiment Index"]
        rename_map = {"brand_name": "Brand"}
    else:
        columns = ["Rank", "product_name", "brand_name", "Visibility Score", "Mention Rate", "Share of Voice", "Top Spot Share", "Sentiment Index"]
        rename_map = {"product_name": "Product", "brand_name": "Brand"}

    st.dataframe(
        display_df[columns].rename(columns=rename_map),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Export Data")

    export_df = df.copy()
    export_df["visibility_score_100"] = export_df["dragon_lens_visibility"] * 100

    csv = export_df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"{name_col.replace('_name', '')}_metrics.csv",
        mime="text/csv",
    )


def _render_brand_view(metrics: dict, user_brands: list[str], comparison: dict = None) -> None:
    if not metrics["brands"]:
        st.info("No brand metrics available yet. The tracking job may still be processing.")
        return

    df = pd.DataFrame(metrics["brands"])
    user_brand = user_brands[0] if user_brands else None

    _render_executive_scorecard(df, "brand_name", user_brand)

    st.markdown("---")

    if comparison:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Competitive Landscape",
            "Performance Analysis",
            "Opportunities",
            "Detailed Data",
            "Comparison Sentiment",
        ])

        with tab5:
            _render_comparison_tab(comparison)
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "Competitive Landscape",
            "Performance Analysis",
            "Opportunities",
            "Detailed Data",
        ])

    with tab1:
        _render_competitive_landscape_tab(df, "brand_name", user_brand)

    with tab2:
        _render_performance_tab(df, "brand_name", user_brand)

    with tab3:
        _render_opportunities_tab(df, "brand_name", user_brand)

    with tab4:
        _render_data_tab(df, "brand_name")


def _render_product_view(metrics: dict, user_brands: list[str], comparison: dict = None) -> None:
    if not metrics["products"]:
        st.info("No product metrics available yet. The tracking job may still be processing.")
        return

    df = pd.DataFrame(metrics["products"])

    user_products = df[df["brand_name"].isin(user_brands)]["product_name"].tolist() if user_brands else []
    user_product = user_products[0] if user_products else None

    _render_executive_scorecard(df, "product_name", user_product)

    st.markdown("---")

    if comparison:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Competitive Landscape",
            "Performance Analysis",
            "Opportunities",
            "Detailed Data",
            "Comparison Sentiment",
        ])

        with tab5:
            _render_comparison_tab(comparison)
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "Competitive Landscape",
            "Performance Analysis",
            "Opportunities",
            "Detailed Data",
        ])

    with tab1:
        _render_competitive_landscape_tab(df, "product_name", user_product)

    with tab2:
        _render_performance_tab(df, "product_name", user_product)

    with tab3:
        _render_opportunities_tab(df, "product_name", user_product)

    with tab4:
        _render_data_tab(df, "product_name")


def show():
    st.title("Brand Visibility Results")

    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/verticals",
            timeout=10.0,
        )
        response.raise_for_status()
        verticals = response.json()

        if not verticals:
            st.warning("No verticals found. Please create a tracking job first.")
            return

    except httpx.HTTPError as e:
        st.error(f"Error fetching verticals: {e}")
        return

    vertical_options = {v["name"]: v["id"] for v in verticals}
    selected_vertical_name = st.selectbox("Select Vertical", list(vertical_options.keys()))
    selected_vertical_id = vertical_options[selected_vertical_name]

    available_models = _fetch_available_models(selected_vertical_id)

    if not available_models:
        st.info("No completed runs found for this vertical yet.")
        return

    model_options = ["All"] + available_models

    col1, col2 = st.columns(2)

    with col1:
        selected_model = st.selectbox("LLM Model", model_options, index=0)

    with col2:
        view_mode = st.radio("View Mode", ["Brand", "Product"], horizontal=True)

    model_param = "all" if selected_model == "All" else selected_model

    user_brands = _fetch_user_brands(selected_vertical_id)

    if model_param == "all":
        with st.spinner("Loading metrics..."):
            metrics = _fetch_metrics(selected_vertical_id, model_param, view_mode)

        if not metrics:
            st.warning("No data found for this vertical and model combination.")
            st.info("Make sure a tracking job has been run and completed.")
            return

        st.subheader(f"{metrics['vertical_name']} ({metrics['model_name']})")
        st.caption(f"Data from: {metrics['date']}")

        comparison = None
    else:
        latest_run = _fetch_latest_completed_run(selected_vertical_id, model_param)
        if not latest_run:
            st.info("No completed runs found for this vertical/model yet.")
            return

        run_id = latest_run["id"]
        st.subheader(f"Latest Run Metrics: {selected_vertical_name} ({model_param})")
        st.caption(f"Run ID: {run_id} | Run time: {latest_run.get('run_time')}")

        with st.spinner("Loading run metrics..."):
            if view_mode == "Brand":
                metrics = _fetch_run_brand_metrics(run_id)
            else:
                metrics = _fetch_run_product_metrics(run_id)

        if not metrics:
            st.error("Failed to load run metrics.")
            return

        include_snippets = st.checkbox("Include comparison snippets", value=False)
        with st.spinner("Loading comparison data..."):
            comparison = _fetch_run_comparison(run_id, include_snippets)

    if view_mode == "Brand":
        _render_brand_view(metrics, user_brands, comparison)
    else:
        _render_product_view(metrics, user_brands, comparison)

    st.markdown("---")
    st.caption("For detailed prompt/answer analysis, visit the **Run Inspector** page.")
