import pandas as pd
import streamlit as st

from ui.components.charts import (
    render_model_heatmap,
    render_positioning_matrix,
    render_sov_bar_chart,
)
from ui.components.insights import render_insights
from ui.components.prompt_gaps import render_prompt_gaps
from ui.utils.api import (
    fetch_available_models,
    fetch_json,
    fetch_user_brands,
    render_vertical_selector,
)


def _fetch_metrics(vertical_id: int, model_name: str, view_mode: str) -> dict | None:
    endpoint = "/api/v1/metrics/latest"
    if view_mode == "Product":
        endpoint = "/api/v1/metrics/latest/products"
    return fetch_json(
        endpoint,
        params={"vertical_id": vertical_id, "model_name": model_name},
    )


def _fetch_latest_completed_run(vertical_id: int, model_name: str) -> dict | None:
    runs = fetch_json(
        "/api/v1/tracking/runs",
        params={"vertical_id": vertical_id, "model_name": model_name, "limit": 50},
        timeout=10.0,
    )
    if not runs:
        return None
    for run in runs:
        if run.get("status") == "completed":
            return run
    return None


def _fetch_run_brand_metrics(run_id: int) -> dict | None:
    data = fetch_json(f"/api/v1/metrics/run/{run_id}")
    if not data:
        return None
    return {"brands": data.get("metrics") or []}


def _fetch_run_product_metrics(run_id: int) -> dict | None:
    return fetch_json(f"/api/v1/metrics/run/{run_id}/products")


def _fetch_run_comparison(run_id: int, include_snippets: bool) -> dict | None:
    return fetch_json(
        f"/api/v1/metrics/run/{run_id}/comparison",
        params={
            "include_snippets": include_snippets,
            "limit_entities": 50,
            "limit_snippets": 3,
        },
        silent=True,
    )


def _fetch_run_comparison_summary(run_id: int, include_prompt_details: bool) -> dict | None:
    return fetch_json(
        f"/api/v1/metrics/run/{run_id}/comparison/summary",
        params={
            "include_prompt_details": include_prompt_details,
            "limit_prompts": 100,
        },
        silent=True,
    )


def _get_sentiment_label(sentiment_index: float) -> str:
    if sentiment_index > 0.3:
        return "Positive"
    elif sentiment_index < -0.3:
        return "Negative"
    return "Neutral"


def _render_executive_scorecard(df: pd.DataFrame, name_col: str, user_brand: str | None = None) -> None:
    if user_brand and user_brand in df[name_col].values:
        user_data = df[df[name_col] == user_brand].iloc[0]
        user_rank = (df["dragon_lens_visibility"] > user_data["dragon_lens_visibility"]).sum() + 1
    else:
        user_data = df.nlargest(1, "dragon_lens_visibility").iloc[0]
        user_rank = 1
        user_brand = user_data[name_col]

    col1, col2, col3 = st.columns(3)

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
        sentiment = user_data["sentiment_index"]
        sentiment_label = _get_sentiment_label(sentiment)
        st.metric(
            "Sentiment",
            sentiment_label,
            f"{sentiment:+.2f}",
            help="Overall sentiment index (-1 to +1)",
        )

    total_brands = len(df)
    mention = user_data["mention_rate"] * 100
    st.caption(
        f"**{user_brand}** · Rank #{user_rank} of {total_brands} · "
        f"Mentioned in {mention:.0f}% of prompts"
    )


def _render_comparison_tab(comparison: dict, comparison_summary: dict | None, run_id: int | None) -> None:
    if comparison_summary:
        st.markdown("### Winners & Losers (Comparison Prompts)")
        st.write(f"Primary brand: **{comparison_summary.get('primary_brand_name', '')}**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Brand Sentiment Index")
            _sentiment_table(comparison_summary.get("brands") or [], "brand")
        with col2:
            st.markdown("#### Product Sentiment Index")
            _sentiment_table(comparison_summary.get("products") or [], "product")

        st.markdown("#### Outcome Summary by Characteristic")
        characteristics = comparison_summary.get("characteristics") or []
        if characteristics:
            df = pd.DataFrame(characteristics).copy()
            cols = [c for c in ["characteristic_en", "total_prompts", "primary_wins", "competitor_wins", "ties", "unknown"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No characteristic summary available.")

        if run_id:
            with st.expander("Prompt details (translated prompts and answers)", expanded=False):
                include_details = st.checkbox("Load prompt details", value=False, key=f"comparison_details_{run_id}")
                if include_details:
                    details = _fetch_run_comparison_summary(run_id, include_prompt_details=True)
                    if details:
                        _render_prompt_outcome_details(details.get("prompts") or [])
                    else:
                        st.info("Prompt details are not available yet.")

    st.markdown("---")
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
    cols = [c for c in ["characteristic_en", "primary_product_name", "competitor_product_name", "winner_role", "winner_product_name", "loser_product_name"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    for r in rows:
        title = f"{r.get('characteristic_en', '')}: {r.get('primary_product_name', '')} vs {r.get('competitor_product_name', '')}"
        winner = r.get("winner_product_name") or r.get("winner_role") or ""
        with st.expander(f"{title} (winner: {winner})"):
            st.markdown("**Prompt (EN)**")
            st.write(r.get("prompt_en") or "")
            st.markdown("**Answer (EN)**")
            st.write(r.get("answer_en") or "")


def _render_dashboard_content(
    df: pd.DataFrame,
    name_col: str,
    user_brand: str | None,
    comparison: dict | None,
    comparison_summary: dict | None,
    run_id: int | None,
    vertical_id: int | None = None,
    available_models: list[str] | None = None,
    user_brand_id: int | None = None,
) -> None:
    _render_executive_scorecard(df, name_col, user_brand)
    st.markdown("---")

    render_positioning_matrix(df, name_col, user_brand)
    st.markdown("---")

    if vertical_id and available_models:
        render_model_heatmap(vertical_id, available_models, name_col, user_brand)
        st.markdown("---")

    col_sov, col_insights = st.columns([3, 2])
    with col_sov:
        render_sov_bar_chart(df, name_col, user_brand)
    with col_insights:
        render_insights(df, name_col, user_brand)

    if run_id:
        with st.expander("Prompt Coverage Analysis", expanded=False):
            render_prompt_gaps(run_id, user_brand_id)

    if comparison or comparison_summary:
        with st.expander("Comparison Details"):
            _render_comparison_tab(comparison or {}, comparison_summary, run_id)


def show() -> None:
    st.title("Dashboard")

    vertical_result = render_vertical_selector()
    if not vertical_result:
        return
    selected_vertical_name, selected_vertical_id = vertical_result

    available_models = fetch_available_models(selected_vertical_id)
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
    user_brand_records = fetch_user_brands(selected_vertical_id)
    user_brand = user_brand_records[0]["display_name"] if user_brand_records else None
    user_brand_id = user_brand_records[0]["id"] if user_brand_records else None

    comparison = None
    comparison_summary = None
    run_id = None

    if model_param == "all":
        with st.spinner("Loading metrics..."):
            metrics = _fetch_metrics(selected_vertical_id, model_param, view_mode)
        if not metrics:
            st.warning("No data found for this vertical and model combination.")
            return

        st.subheader(f"{metrics['vertical_name']} ({metrics['model_name']})")
        st.caption(f"Data from: {metrics['date']}")
    else:
        latest_run = _fetch_latest_completed_run(selected_vertical_id, model_param)
        if not latest_run:
            st.info("No completed runs found for this vertical/model yet.")
            return

        run_id = latest_run["id"]
        st.subheader(f"Latest Run: {selected_vertical_name} ({model_param})")
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
            comparison_summary = _fetch_run_comparison_summary(run_id, include_prompt_details=False)

    items_key = "brands" if view_mode == "Brand" else "products"
    items = metrics.get(items_key) or []
    if not items:
        st.info(f"No {view_mode.lower()} metrics available yet. The tracking job may still be processing.")
        return

    df = pd.DataFrame(items)
    name_col = "brand_name" if view_mode == "Brand" else "product_name"

    user_brand_names = [b["display_name"] for b in user_brand_records]
    if view_mode == "Product" and user_brand_names:
        user_products = df[df["brand_name"].isin(user_brand_names)]["product_name"].tolist()
        user_entity = user_products[0] if user_products else None
    else:
        user_entity = user_brand

    _render_dashboard_content(
        df, name_col, user_entity, comparison, comparison_summary, run_id,
        vertical_id=selected_vertical_id, available_models=available_models,
        user_brand_id=user_brand_id,
    )
