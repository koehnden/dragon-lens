import httpx
import pandas as pd
import streamlit as st

from config import settings


def _render_brand_view(metrics: dict) -> None:
    if not metrics["brands"]:
        st.info("No brand metrics available yet. The tracking job may still be processing.")
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

    st.markdown("### Brands Overview")
    display_df = df.copy()
    display_df = display_df.sort_values("dragon_lens_visibility", ascending=False)
    display_df["mention_rate"] = (display_df["mention_rate"] * 100).round(1).astype(str) + "%"
    display_df["share_of_voice"] = (display_df["share_of_voice"] * 100).round(1).astype(str) + "%"
    display_df["top_spot_share"] = (display_df["top_spot_share"] * 100).round(1).astype(str) + "%"
    display_df["sentiment_index"] = display_df["sentiment_index"].round(3)
    display_df["dragon_lens_visibility"] = display_df["dragon_lens_visibility"].round(3)

    st.dataframe(
        display_df[[
            "brand_name",
            "mention_rate",
            "share_of_voice",
            "top_spot_share",
            "sentiment_index",
            "dragon_lens_visibility",
        ]].rename(columns={
            "brand_name": "Brand",
            "mention_rate": "Mention Rate",
            "share_of_voice": "Share of Voice",
            "top_spot_share": "Top Spot Share",
            "sentiment_index": "Sentiment Index",
            "dragon_lens_visibility": "DVS",
        }),
        use_container_width=True,
        hide_index=True,
    )

    _render_charts(df, "brand_name")


def _render_product_view(metrics: dict) -> None:
    if not metrics["products"]:
        st.info("No product metrics available yet. The tracking job may still be processing.")
        return

    df = pd.DataFrame(metrics["products"])

    st.markdown("### Product Mention Overview")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Products", len(df))

    with col2:
        avg_mention = df["mention_rate"].mean() * 100
        st.metric("Avg Mention Rate", f"{avg_mention:.1f}%")

    with col3:
        mentioned_products = (df["mention_rate"] > 0).sum()
        st.metric("Products Mentioned", mentioned_products)

    st.markdown("### Products Overview")
    display_df = df.copy()
    display_df = display_df.sort_values("dragon_lens_visibility", ascending=False)
    display_df["mention_rate"] = (display_df["mention_rate"] * 100).round(1).astype(str) + "%"
    display_df["share_of_voice"] = (display_df["share_of_voice"] * 100).round(1).astype(str) + "%"
    display_df["top_spot_share"] = (display_df["top_spot_share"] * 100).round(1).astype(str) + "%"
    display_df["sentiment_index"] = display_df["sentiment_index"].round(3)
    display_df["dragon_lens_visibility"] = display_df["dragon_lens_visibility"].round(3)

    st.dataframe(
        display_df[[
            "product_name",
            "brand_name",
            "mention_rate",
            "share_of_voice",
            "top_spot_share",
            "sentiment_index",
            "dragon_lens_visibility",
        ]].rename(columns={
            "product_name": "Product",
            "brand_name": "Brand",
            "mention_rate": "Mention Rate",
            "share_of_voice": "Share of Voice",
            "top_spot_share": "Top Spot Share",
            "sentiment_index": "Sentiment Index",
            "dragon_lens_visibility": "DVS",
        }),
        use_container_width=True,
        hide_index=True,
    )

    _render_charts(df, "product_name")


def _render_charts(df: pd.DataFrame, name_col: str) -> None:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### Mention Rate by {name_col.replace('_', ' ').title()}")
        chart_data = df[[name_col, "mention_rate"]].copy()
        chart_data["mention_rate"] = chart_data["mention_rate"] * 100
        st.bar_chart(chart_data.set_index(name_col))

    with col2:
        st.markdown("### Share of Voice")
        sov_data = df[[name_col, "share_of_voice"]].copy()
        sov_data["share_of_voice"] = sov_data["share_of_voice"] * 100
        st.bar_chart(sov_data.set_index(name_col))

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Dragon Lens Visibility (DVS)")
        dvs_chart = df[[name_col, "dragon_lens_visibility"]].copy()
        dvs_chart = dvs_chart.sort_values("dragon_lens_visibility", ascending=False)
        dvs_chart = dvs_chart.set_index(name_col)
        st.bar_chart(dvs_chart)

    with col2:
        st.markdown("### Sentiment Index")
        sent_chart = df[[name_col, "sentiment_index"]].copy()
        sent_chart = sent_chart.sort_values("sentiment_index", ascending=False)
        sent_chart = sent_chart.set_index(name_col)
        st.bar_chart(sent_chart)


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


def _render_comparison_view(comparison: dict) -> None:
    st.markdown("### Comparison Sentiment (Run)")
    st.write(f"Primary brand: {comparison.get('primary_brand_name', '')}")
    messages = comparison.get("messages") or []
    if messages:
        with st.expander("Messages"):
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

    run_id = None
    if model_param == "all":
        with st.spinner("Loading metrics..."):
            metrics = _fetch_metrics(selected_vertical_id, model_param, view_mode)
        if not metrics:
            st.warning("No data found for this vertical and model combination.")
            st.info("Make sure a tracking job has been run and completed.")
            return
        st.subheader(f"Latest Metrics: {metrics['vertical_name']} ({metrics['model_name']})")
        st.caption(f"Data from: {metrics['date']}")
        if view_mode == "Brand":
            _render_brand_view(metrics)
        else:
            _render_product_view(metrics)
        st.info("Comparison results are available for a specific model/run.")
    else:
        latest_run = _fetch_latest_completed_run(selected_vertical_id, model_param)
        if not latest_run:
            st.info("No completed runs found for this vertical/model yet.")
            return
        run_id = latest_run["id"]
        st.subheader(f"Latest Run Metrics: {selected_vertical_name} ({model_param})")
        st.caption(f"Run ID: {run_id} | Run time: {latest_run.get('run_time')}")
        with st.spinner("Loading run metrics..."):
            metrics = _fetch_run_brand_metrics(run_id) if view_mode == "Brand" else _fetch_run_product_metrics(run_id)
        if not metrics:
            st.error("Failed to load run metrics.")
            return
        if view_mode == "Brand":
            _render_brand_view(metrics)
        else:
            _render_product_view(metrics)
        include_snippets = st.checkbox("Include comparison snippets", value=False)
        with st.spinner("Loading comparison sentiment..."):
            comparison = _fetch_run_comparison(run_id, include_snippets)
        if comparison:
            _render_comparison_view(comparison)

    st.markdown("---")
    st.markdown("## Last Run Inspector")
    st.caption("View raw answers and extracted brand mentions from the most recent run")

    _render_run_inspector(selected_vertical_id, model_param)


def _render_run_inspector(vertical_id: int, model_name: str) -> None:
    try:
        params = {"vertical_id": vertical_id, "limit": 1}
        if model_name != "all":
            params["model_name"] = model_name

        runs_response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/tracking/runs",
            params=params,
            timeout=10.0,
        )
        runs_response.raise_for_status()
        runs = runs_response.json()

        if not runs:
            st.info("No runs found for this vertical and model.")
            return

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
            st.info("No answers available for this run yet. The job may still be processing.")
            return

        for i, answer in enumerate(run_details["answers"], 1):
            with st.expander(f"Prompt & Answer {i}", expanded=(i == 1)):
                _render_answer_details(answer, i)

    except httpx.HTTPError as e:
        st.error(f"Error fetching run details: {e}")
    except Exception as e:
        st.error(f"Unexpected error loading run inspector: {e}")


def _render_answer_details(answer: dict, index: int) -> None:
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
            key=f"answer_zh_{index}",
            label_visibility="collapsed",
        )
    with col2:
        st.markdown("**English Translation:**")
        st.text_area(
            "English",
            answer.get("raw_answer_en") or "_Translation not available_",
            height=150,
            key=f"answer_en_{index}",
            label_visibility="collapsed",
        )

    st.markdown("---")
    st.markdown("#### Brand Mentions Detected")

    if not answer["mentions"]:
        st.info("No brand mentions detected in this answer.")
        return

    mentioned_brands = [m for m in answer["mentions"] if m["mentioned"]]
    if not mentioned_brands:
        st.info("No brands were mentioned in this answer.")
        return

    for mention in mentioned_brands:
        _render_mention(mention)


def _render_mention(mention: dict) -> None:
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
