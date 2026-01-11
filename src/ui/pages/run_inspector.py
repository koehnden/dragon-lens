import logging

import httpx
import streamlit as st

from config import settings
from ui.utils.run_formatting import format_run_option_label


logger = logging.getLogger(__name__)


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
            key=f"inspector_answer_zh_{index}",
            label_visibility="collapsed",
        )
    with col2:
        st.markdown("**English Translation:**")
        st.text_area(
            "English",
            answer.get("raw_answer_en") or "_Translation not available_",
            height=150,
            key=f"inspector_answer_en_{index}",
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
        "positive": "positive",
        "neutral": "neutral",
        "negative": "negative",
    }.get(mention["sentiment"], "")

    rank_text = f"Rank #{mention['rank']}" if mention.get("rank") else "No rank"
    st.markdown(
        f"**{mention['brand_name']}** "
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


def _render_run_details(run_details: dict) -> None:
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


def show():
    st.title("Run Inspector")
    st.caption("View raw answers and extracted brand mentions from tracking runs")

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
    selected_model = st.selectbox("LLM Model", model_options, index=0)
    model_param = "all" if selected_model == "All" else selected_model

    try:
        params = {"vertical_id": selected_vertical_id, "limit": 10}
        if model_param != "all":
            params["model_name"] = model_param

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

        run_options = {format_run_option_label(r): r["id"] for r in runs}
        selected_run_label = st.selectbox("Select Run", list(run_options.keys()))
        selected_run_id = run_options[selected_run_label]

        with st.spinner("Loading run details..."):
            details_response = httpx.get(
                f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{selected_run_id}/details",
                timeout=30.0,
            )
            details_response.raise_for_status()
            run_details = details_response.json()

        _render_run_details(run_details)

    except httpx.HTTPError as e:
        st.error(f"Error fetching run details: {e}")
    except Exception as e:
        logger.exception("Unexpected error loading run inspector")
        st.error(f"Unexpected error loading run inspector: {e}")
