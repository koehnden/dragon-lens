import json
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


def _fetch_run_export(run_id: int) -> list[dict]:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}/inspector-export",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_vertical_export(vertical_id: int) -> list[dict]:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/inspector-export",
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def _encode_json_for_download(data: list[dict]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _start_ai_correction(run_id: int, provider: str, model_name: str, dry_run: bool) -> dict:
    response = httpx.post(
        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}/ai-corrections",
        json={"provider": provider, "model_name": model_name, "dry_run": dry_run},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_latest_ai_correction(run_id: int) -> dict | None:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}/ai-corrections",
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_ai_correction_report(run_id: int, audit_id: int) -> dict:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}/ai-corrections/{audit_id}/report",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _apply_ai_review_item(run_id: int, audit_id: int, item_id: int) -> dict:
    response = httpx.post(
        f"http://localhost:{settings.api_port}/api/v1/tracking/runs/{run_id}/ai-corrections/{audit_id}/review-items/{item_id}/apply",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _start_vertical_ai_correction(vertical_id: int, provider: str, model_name: str) -> dict:
    response = httpx.post(
        f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/ai-corrections",
        json={"provider": provider, "model_name": model_name, "dry_run": True},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_latest_vertical_ai_correction(vertical_id: int) -> dict | None:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/ai-corrections",
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_vertical_ai_correction_report(vertical_id: int, audit_id: int) -> dict:
    response = httpx.get(
        f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/ai-corrections/{audit_id}/report",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _apply_vertical_ai_review_item(vertical_id: int, audit_id: int, item_id: int) -> dict:
    response = httpx.post(
        f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}/ai-corrections/{audit_id}/review-items/{item_id}/apply",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _fetch_feedback_candidates(vertical_id: int) -> dict | None:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/feedback/candidates",
            params={"vertical_id": vertical_id},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _fetch_knowledge_verticals() -> list[dict]:
    try:
        response = httpx.get(
            f"http://localhost:{settings.api_port}/api/v1/knowledge/verticals",
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []


def _save_vertical_alias(vertical_id: int, canonical: dict) -> dict:
    response = httpx.post(
        f"http://localhost:{settings.api_port}/api/v1/feedback/vertical-alias",
        json={"vertical_id": vertical_id, "canonical_vertical": canonical},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _canonical_vertical_input(knowledge_verticals: list[dict], key_prefix: str) -> dict:
    names = [v["name"] for v in knowledge_verticals if v.get("name")]
    options = names + ["Create new"] if names else ["Create new"]
    choice = st.selectbox("Canonical Group", options, key=f"{key_prefix}_canonical_choice")
    if choice == "Create new":
        name = st.text_input("New Canonical Group", key=f"{key_prefix}_canonical_new")
        return {"is_new": True, "name": name.strip()}
    match = next((v for v in knowledge_verticals if v.get("name") == choice), None)
    return {"is_new": False, "id": match.get("id") if match else None}


def _canonical_error(canonical: dict) -> str:
    if canonical.get("is_new") and not canonical.get("name"):
        return "Canonical group name is required."
    if not canonical.get("is_new") and not canonical.get("id"):
        return "Select a canonical group."
    return ""


def _maybe_set_canonical_group(vertical_id: int) -> None:
    candidates = _fetch_feedback_candidates(vertical_id) or {}
    resolved = candidates.get("resolved_canonical_vertical_name")
    if resolved:
        st.caption(f"Canonical group: {resolved}")
        return
    st.info("No canonical group is set for this vertical yet. Set one to share improvements across similar verticals.")
    knowledge_verticals = _fetch_knowledge_verticals()
    canonical = _canonical_vertical_input(knowledge_verticals, key_prefix=f"inspector_map_{vertical_id}")
    if st.button("Save Canonical Group", key=f"inspector_save_canonical_{vertical_id}"):
        error = _canonical_error(canonical)
        if error:
            st.error(error)
            return
        _save_vertical_alias(vertical_id, canonical)
        st.success("Canonical group saved.")
        st.rerun()


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

    if st.button("Export for Vertical"):
        try:
            with st.spinner("Building vertical export..."):
                export_data = _fetch_vertical_export(selected_vertical_id)
            st.download_button(
                label="Download Vertical JSON",
                data=_encode_json_for_download(export_data),
                file_name=f"run_inspector_{selected_vertical_name}_vertical.json",
                mime="application/json",
            )
        except httpx.HTTPError as e:
            st.error(f"Error building vertical export: {e}")

    available_models = _fetch_available_models(selected_vertical_id)

    if not available_models:
        st.info("No completed runs found for this vertical yet.")
        return

    model_options = ["All"] + available_models
    selected_model = st.selectbox("LLM Model", model_options, index=0)
    if selected_model == "All":
        st.markdown("---")
        st.subheader("AI Corrections (Vertical)")
        _maybe_set_canonical_group(selected_vertical_id)
        provider = st.selectbox(
            "AI Model Provider",
            ["deepseek", "kimi", "openrouter"],
            index=0,
            key=f"vertical_ai_provider_{selected_vertical_id}",
        )
        if provider == "deepseek":
            model_name = st.selectbox(
                "AI Model",
                ["deepseek-reasoner", "deepseek-chat"],
                index=0,
                key=f"vertical_ai_model_{selected_vertical_id}",
            )
        elif provider == "kimi":
            model_name = st.text_input("AI Model", value="moonshot-v1-8k", key=f"vertical_ai_model_{selected_vertical_id}")
        else:
            model_name = st.text_input("AI Model", value="openrouter/auto", key=f"vertical_ai_model_{selected_vertical_id}")

        st.caption("Dry run is enabled for vertical corrections.")

        audit_state_key = f"ai_corrections_vertical_audit_{selected_vertical_id}"
        if audit_state_key not in st.session_state:
            st.session_state[audit_state_key] = None

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Correct Vertical with AI", key=f"vertical_ai_start_{selected_vertical_id}"):
                try:
                    with st.spinner("Starting AI correction..."):
                        audit = _start_vertical_ai_correction(selected_vertical_id, provider, model_name)
                    st.session_state[audit_state_key] = audit
                except httpx.HTTPError as e:
                    st.error(f"Error starting AI correction: {e}")

        with col2:
            if st.button("Refresh AI correction status", key=f"vertical_ai_refresh_{selected_vertical_id}"):
                try:
                    audit = _fetch_latest_vertical_ai_correction(selected_vertical_id)
                    st.session_state[audit_state_key] = audit
                except httpx.HTTPError as e:
                    st.error(f"Error fetching AI correction status: {e}")

        audit = st.session_state.get(audit_state_key)
        if audit:
            st.write(
                f"Status: `{audit.get('status')}` | Resolved: `{audit.get('resolved_provider')}:{audit.get('resolved_model')}`"
            )
            if audit.get("status") == "completed":
                report = _fetch_vertical_ai_correction_report(selected_vertical_id, int(audit.get("audit_id") or 0))
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Brands Precision", report["brands"]["precision"])
                    st.metric("Brands Recall", report["brands"]["recall"])
                with m2:
                    st.metric("Products Precision", report["products"]["precision"])
                    st.metric("Products Recall", report["products"]["recall"])
                with m3:
                    st.metric("Mappings Precision", report["mappings"]["precision"])
                    st.metric("Mappings Recall", report["mappings"]["recall"])

                st.markdown("#### Common Mistakes")
                if report.get("clusters"):
                    vertical_export = _fetch_vertical_export(selected_vertical_id)
                    export_by_answer = {int(i.get("llm_answer_id") or 0): i for i in vertical_export}
                    for cluster in report["clusters"]:
                        with st.expander(f"{cluster['category']} ({cluster['count']})"):
                            for example in cluster.get("examples") or []:
                                answer = export_by_answer.get(int(example) if str(example).isdigit() else 0)
                                if not answer:
                                    st.write(f"Example llm_answer_id: {example}")
                                    continue
                                st.write(answer.get("prompt_zh") or "")
                                st.write(answer.get("prompt_response_zh") or "")
                else:
                    st.info("No clusters available for this audit run.")

                st.markdown("#### Needs Human Review")
                pending = report.get("pending_review_items") or []
                if not pending:
                    st.success("No pending review items.")
                for item in pending:
                    st.markdown(
                        f"Run `{item.get('run_id')}` | **{item.get('category')}** | `{item.get('action')}` | "
                        f"{item.get('confidence_level')} ({item.get('confidence_score')})"
                    )
                    st.write(item.get("reason") or "")
                    if item.get("evidence_quote_zh"):
                        st.caption(f"Evidence: {item.get('evidence_quote_zh')}")
                    with st.expander("Feedback payload"):
                        st.json(item.get("feedback_payload") or {})
                    if st.button("Apply", key=f"apply_vertical_ai_review_item_{audit.get('audit_id')}_{item['id']}"):
                        try:
                            _apply_vertical_ai_review_item(selected_vertical_id, int(audit.get("audit_id") or 0), int(item["id"]))
                            st.success("Applied feedback.")
                            st.session_state[audit_state_key] = _fetch_latest_vertical_ai_correction(selected_vertical_id)
                        except httpx.HTTPError as e:
                            st.error(f"Error applying review item: {e}")
            elif audit.get("status") == "failed":
                st.error("AI correction failed. Check API logs for details.")
            else:
                st.info("AI correction is running. Refresh status to see results.")
        return

    model_param = selected_model

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

        if st.button("Export JSON (selected run)"):
            try:
                with st.spinner("Building run export..."):
                    export_data = _fetch_run_export(selected_run_id)
                st.download_button(
                    label="Download Run JSON",
                    data=_encode_json_for_download(export_data),
                    file_name=f"run_inspector_{selected_vertical_name}_{selected_model}_run_{selected_run_id}.json",
                    mime="application/json",
                )
            except httpx.HTTPError as e:
                st.error(f"Error building run export: {e}")

        st.markdown("---")
        st.subheader("AI Corrections")

        provider = st.selectbox(
            "AI Model Provider",
            ["deepseek", "kimi", "openrouter"],
            index=0,
        )
        if provider == "deepseek":
            model_name = st.selectbox("AI Model", ["deepseek-reasoner", "deepseek-chat"], index=0)
        elif provider == "kimi":
            model_name = st.text_input("AI Model", value="moonshot-v1-8k")
        else:
            model_name = st.text_input("AI Model", value="openrouter/auto")

        dry_run = st.checkbox("Dry run (no auto-apply)", value=False)

        audit_state_key = f"ai_corrections_audit_{selected_run_id}"
        if audit_state_key not in st.session_state:
            st.session_state[audit_state_key] = None

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Correct with AI"):
                try:
                    with st.spinner("Starting AI correction..."):
                        audit = _start_ai_correction(selected_run_id, provider, model_name, dry_run)
                    st.session_state[audit_state_key] = audit
                except httpx.HTTPError as e:
                    st.error(f"Error starting AI correction: {e}")

        with col2:
            if st.button("Refresh AI correction status"):
                try:
                    audit = _fetch_latest_ai_correction(selected_run_id)
                    st.session_state[audit_state_key] = audit
                except httpx.HTTPError as e:
                    st.error(f"Error fetching AI correction status: {e}")

        audit = st.session_state.get(audit_state_key)
        if audit:
            st.write(
                f"Status: `{audit.get('status')}` | Resolved: `{audit.get('resolved_provider')}:{audit.get('resolved_model')}`"
            )
            if audit.get("status") == "completed":
                report = _fetch_ai_correction_report(selected_run_id, int(audit.get("audit_id") or 0))
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Brands Precision", report["brands"]["precision"])
                    st.metric("Brands Recall", report["brands"]["recall"])
                with m2:
                    st.metric("Products Precision", report["products"]["precision"])
                    st.metric("Products Recall", report["products"]["recall"])
                with m3:
                    st.metric("Mappings Precision", report["mappings"]["precision"])
                    st.metric("Mappings Recall", report["mappings"]["recall"])

                st.markdown("#### Common Mistakes")
                if report.get("clusters"):
                    run_export = _fetch_run_export(selected_run_id)
                    export_by_answer = {int(i.get("llm_answer_id") or 0): i for i in run_export}
                    for cluster in report["clusters"]:
                        with st.expander(f"{cluster['category']} ({cluster['count']})"):
                            for example in cluster.get("examples") or []:
                                answer = export_by_answer.get(int(example) if str(example).isdigit() else 0)
                                if not answer:
                                    st.write(f"Example llm_answer_id: {example}")
                                    continue
                                st.write(answer.get("prompt_zh") or "")
                                st.write(answer.get("prompt_response_zh") or "")
                else:
                    st.info("No clusters available for this audit run.")

                st.markdown("#### Needs Human Review")
                pending = report.get("pending_review_items") or []
                if not pending:
                    st.success("No pending review items.")
                for item in pending:
                    st.markdown(
                        f"**{item.get('category')}** | `{item.get('action')}` | "
                        f"{item.get('confidence_level')} ({item.get('confidence_score')})"
                    )
                    st.write(item.get("reason") or "")
                    if item.get("evidence_quote_zh"):
                        st.caption(f"Evidence: {item.get('evidence_quote_zh')}")
                    with st.expander("Feedback payload"):
                        st.json(item.get("feedback_payload") or {})
                    if st.button("Apply", key=f"apply_ai_review_item_{audit.get('audit_id')}_{item['id']}"):
                        try:
                            _apply_ai_review_item(selected_run_id, int(audit.get("audit_id") or 0), int(item["id"]))
                            st.success("Applied feedback.")
                            st.session_state[audit_state_key] = _fetch_latest_ai_correction(selected_run_id)
                        except httpx.HTTPError as e:
                            st.error(f"Error applying review item: {e}")
            elif audit.get("status") == "failed":
                st.error("AI correction failed. Check API logs for details.")
            else:
                st.info("AI correction is running. Refresh status to see results.")

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
