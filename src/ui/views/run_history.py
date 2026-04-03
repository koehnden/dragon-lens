import json
import logging

import httpx
import pandas as pd
import streamlit as st

from ui.utils.api import (
    fetch_available_models,
    fetch_json,
    render_vertical_selector,
)
from ui.utils.run_formatting import format_run_option_label


logger = logging.getLogger(__name__)


def _fetch_runs(vertical_id: int | None = None, model_name: str | None = None) -> list[dict]:
    params: dict = {}
    if vertical_id:
        params["vertical_id"] = vertical_id
    if model_name:
        params["model_name"] = model_name
    return fetch_json("/api/v1/tracking/runs", params=params) or []


def _fetch_run_details(run_id: int) -> dict | None:
    return fetch_json(f"/api/v1/tracking/runs/{run_id}/details")


def _fetch_run_export(run_id: int) -> list[dict] | None:
    return fetch_json(f"/api/v1/tracking/runs/{run_id}/inspector-export")


def _fetch_vertical_export(vertical_id: int) -> list[dict] | None:
    return fetch_json(f"/api/v1/verticals/{vertical_id}/inspector-export", timeout=60.0)


def _status_icon(status: str) -> str:
    return {
        "completed": "🟢",
        "in_progress": "🟡",
        "failed": "🔴",
    }.get(status, "⚪")


def _render_runs_table(runs: list[dict]) -> None:
    df = pd.DataFrame(runs)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Runs", len(df))
    with col2:
        st.metric("Completed", (df["status"] == "completed").sum())
    with col3:
        st.metric("Failed", (df["status"] == "failed").sum())
    with col4:
        st.metric("In Progress", (df["status"] == "in_progress").sum())

    display_df = df.copy()
    display_df[""] = display_df["status"].apply(_status_icon)
    display_df = display_df[["id", "", "status", "vertical_id", "model_name", "run_time", "completed_at"]]
    display_df.columns = ["Run ID", "", "Status", "Vertical ID", "Model", "Started At", "Completed At"]

    st.dataframe(display_df, use_container_width=True, hide_index=True)


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
            key=f"history_answer_zh_{index}",
            label_visibility="collapsed",
        )
    with col2:
        st.markdown("**English Translation:**")
        st.text_area(
            "English",
            answer.get("raw_answer_en") or "_Translation not available_",
            height=150,
            key=f"history_answer_en_{index}",
            label_visibility="collapsed",
        )

    st.markdown("---")
    st.markdown("#### Brand Mentions Detected")
    mentioned_brands = [m for m in answer.get("mentions") or [] if m.get("mentioned")]
    if not mentioned_brands:
        st.info("No brands were mentioned in this answer.")
        return

    for mention in mentioned_brands:
        _render_mention(mention)


def _render_mention(mention: dict) -> None:
    rank_text = f"Rank #{mention['rank']}" if mention.get("rank") else "No rank"
    st.markdown(
        f"**{mention['brand_name']}** "
        f"| {mention['sentiment'].upper()} | {rank_text}"
    )

    zh_snippets = (mention.get("evidence_snippets") or {}).get("zh", [])
    en_snippets = (mention.get("evidence_snippets") or {}).get("en", [])

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


def _render_run_detail(run_details: dict, vertical_name: str, vertical_id: int) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Run ID", run_details["id"])
    with col2:
        st.metric("Status", run_details["status"])
    with col3:
        st.metric("Prompts Answered", len(run_details.get("answers") or []))

    tab_prompts, tab_export = st.tabs(["Prompts & Answers", "Export"])

    with tab_prompts:
        answers = run_details.get("answers") or []
        if not answers:
            st.info("No answers available for this run yet. The job may still be processing.")
        else:
            for i, answer in enumerate(answers, 1):
                with st.expander(f"Prompt & Answer {i}", expanded=(i == 1)):
                    _render_answer_details(answer, i)

    with tab_export:
        run_id = run_details["id"]
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Export Run JSON", key=f"export_run_{run_id}"):
                try:
                    with st.spinner("Building run export..."):
                        export_data = _fetch_run_export(run_id)
                    if export_data:
                        export_json = json.dumps(export_data, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="Download Run JSON",
                            data=export_json,
                            file_name=f"run_{run_id}_{vertical_name}.json",
                            mime="application/json",
                            key=f"dl_run_{run_id}",
                        )
                except httpx.HTTPError as e:
                    st.error(f"Error building run export: {e}")

        with col2:
            if st.button("Export Vertical JSON", key=f"export_vertical_{vertical_id}"):
                try:
                    with st.spinner("Building vertical export..."):
                        export_data = _fetch_vertical_export(vertical_id)
                    if export_data:
                        export_json = json.dumps(export_data, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="Download Vertical JSON",
                            data=export_json,
                            file_name=f"vertical_{vertical_name}.json",
                            mime="application/json",
                            key=f"dl_vertical_{vertical_id}",
                        )
                except httpx.HTTPError as e:
                    st.error(f"Error building vertical export: {e}")


def show() -> None:
    st.title("Run History")

    vertical_result = render_vertical_selector()
    if not vertical_result:
        return
    selected_vertical_name, selected_vertical_id = vertical_result

    available_models = fetch_available_models(selected_vertical_id)
    model_options = ["All"] + available_models
    selected_model = st.selectbox("Filter by Model", model_options, index=0)
    model_filter = None if selected_model == "All" else selected_model

    try:
        runs = _fetch_runs(selected_vertical_id, model_filter)
        if not runs:
            st.info("No runs found matching the filters.")
            return

        _render_runs_table(runs)

        st.markdown("---")
        st.subheader("Run Details")

        run_options = {format_run_option_label(r): r["id"] for r in runs}
        selected_run_label = st.selectbox("Select Run", list(run_options.keys()))
        selected_run_id = run_options[selected_run_label]

        with st.spinner("Loading run details..."):
            run_details = _fetch_run_details(selected_run_id)
        if not run_details:
            st.error("Failed to load run details.")
            return

        _render_run_detail(run_details, selected_vertical_name, selected_vertical_id)

    except Exception as e:
        logger.exception("Unexpected error in run history")
        st.error(f"Unexpected error: {e}")
