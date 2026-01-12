import httpx
import pandas as pd
import streamlit as st

from config import settings
from ui.feedback_payload import build_feedback_payload

ACTION_OPTIONS = ["", "valid", "wrong"]
MAPPING_ACTIONS = ["", "valid", "wrong"]
MISSING_MAPPING_ACTIONS = ["", "add"]
ENTITY_OPTIONS = ["brand", "product"]
LANG_OPTIONS = ["en"]

STATE_CONTEXT_KEY = "feedback_context_key"
STATE_BRANDS = "feedback_brands"
STATE_PRODUCTS = "feedback_products"
STATE_MAPPINGS = "feedback_mappings"
STATE_MISSING = "feedback_missing_mappings"
STATE_TRANSLATIONS = "feedback_translations"


def show():
    st.title("Feedback")
    context = _context()
    if not context:
        return
    _vertical_mapping_form(context)
    _ensure_state(context)
    _render_form(context)


def _context():
    vertical = _vertical_context()
    if not vertical:
        return None
    candidates = _fetch_candidates(vertical["id"])
    if not candidates:
        return None
    return {
        "vertical": vertical,
        "latest_run_id": candidates.get("latest_completed_run_id"),
        "candidates": candidates,
        "knowledge_verticals": _fetch_knowledge_verticals(),
        "vertical_brands": _fetch_vertical_brands(vertical["id"]),
        "state_key": _state_key(
            vertical["id"], candidates.get("latest_completed_run_id")
        ),
    }


def _state_key(vertical_id: int, run_id: int | None) -> str:
    return f"{vertical_id}:{run_id or 0}"


def _vertical_context():
    verticals = _fetch_verticals()
    if not verticals:
        st.info("No verticals found. Create a tracking job first.")
        return None
    return _select_vertical(verticals)


def _select_vertical(verticals):
    options = {v["name"]: v for v in verticals}
    name = st.selectbox("Vertical", list(options.keys()))
    return options.get(name)


def _render_form(context):
    _summary(context)
    form_state = _feedback_form(context)
    _handle_submit(context, form_state)


def _summary(context):
    run_id = context.get("latest_run_id")
    vertical_name = context["vertical"]["name"]
    group_ids = context["candidates"].get("group_vertical_ids") or []
    st.caption(
        f"Vertical {vertical_name} | Group verticals {len(group_ids)} | Latest run {run_id or 'N/A'}"
    )
    candidates = context["candidates"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Brands", len(candidates.get("brands") or []))
    col2.metric("Products", len(candidates.get("products") or []))
    col3.metric("Mappings", len(candidates.get("mappings") or []))
    col4.metric("Translations", len(candidates.get("translations") or []))


def _feedback_form(context):
    with st.form("feedback_form"):
        canonical = _canonical_vertical_input(
            context["knowledge_verticals"],
            default_name=context["candidates"].get("resolved_canonical_vertical_name"),
            key_prefix="submit",
        )
        _brands_section()
        _products_section()
        _mapping_section()
        _missing_mapping_section(context)
        _translation_section()
        submitted = st.form_submit_button("Submit Feedback")
    return {"submitted": submitted, "canonical": canonical}


def _handle_submit(context, form_state):
    if not form_state["submitted"]:
        return
    error = _canonical_error(form_state["canonical"])
    if error:
        st.error(error)
        return
    if not context.get("latest_run_id"):
        st.error("No completed runs found for this vertical.")
        return
    payload = _payload_from_state(context, form_state["canonical"])
    response = _post_json("/api/v1/feedback/submit", payload)
    if not response:
        return
    st.success("Feedback submitted.")
    _reset_state()
    st.rerun()


def _payload_from_state(context, canonical):
    return build_feedback_payload(
        context["latest_run_id"],
        context["vertical"]["id"],
        canonical,
        _rows(STATE_BRANDS),
        _rows(STATE_PRODUCTS),
        _rows(STATE_MAPPINGS),
        _rows(STATE_MISSING),
        _rows(STATE_TRANSLATIONS),
    )


def _canonical_vertical_input(knowledge_verticals, default_name=None, key_prefix=""):
    options = _canonical_options(knowledge_verticals)
    choice = st.selectbox(
        "Canonical Vertical",
        options,
        index=_canonical_index(options, default_name),
        key=f"{key_prefix}_canonical_choice",
    )
    if choice == "Create new":
        name = st.text_input(
            "New Canonical Vertical", key=f"{key_prefix}_canonical_new"
        )
        return {"is_new": True, "name": name.strip()}
    return _canonical_existing(knowledge_verticals, choice)


def _canonical_index(options, default_name):
    if not default_name:
        return 0
    try:
        return options.index(default_name)
    except ValueError:
        return 0


def _canonical_options(verticals):
    names = [v["name"] for v in verticals]
    return names + ["Create new"] if names else ["Create new"]


def _canonical_existing(verticals, name):
    match = next((v for v in verticals if v["name"] == name), None)
    return {"is_new": False, "id": match["id"] if match else None}


def _canonical_error(canonical):
    if canonical.get("is_new") and not canonical.get("name"):
        return "Canonical vertical name is required."
    if not canonical.get("is_new") and not canonical.get("id"):
        return "Select a canonical vertical."
    return ""


def _vertical_mapping_form(context):
    with st.form("vertical_mapping_form"):
        st.subheader("Vertical Grouping")
        canonical = _canonical_vertical_input(
            context["knowledge_verticals"],
            default_name=context["candidates"].get("resolved_canonical_vertical_name"),
            key_prefix="mapping",
        )
        submitted = st.form_submit_button("Save Vertical Mapping")
    if submitted:
        _save_vertical_mapping(context, canonical)


def _save_vertical_mapping(context, canonical):
    error = _canonical_error(canonical)
    if error:
        st.error(error)
        return
    payload = {
        "vertical_id": context["vertical"]["id"],
        "canonical_vertical": canonical,
    }
    response = _post_json("/api/v1/feedback/vertical-alias", payload)
    if response:
        st.success("Vertical mapping saved.")
        _reset_state()
        st.rerun()


def _brands_section():
    st.subheader("Brands")
    return _edit_table(STATE_BRANDS, _brand_columns())


def _products_section():
    st.subheader("Products")
    return _edit_table(STATE_PRODUCTS, _product_columns())


def _mapping_section():
    st.subheader("Current Mappings")
    return _edit_table(STATE_MAPPINGS, _mapping_columns())


def _missing_mapping_section(context):
    st.subheader("Missing Mappings")
    products = _product_options(context["candidates"])
    brands = _brand_options(context["vertical_brands"])
    columns = _missing_mapping_columns(products, brands)
    return _edit_table(STATE_MISSING, columns, num_rows="dynamic")


def _translation_section():
    st.subheader("Translations")
    return _edit_table(STATE_TRANSLATIONS, _translation_columns(), num_rows="dynamic")


def _edit_table(key, columns, **kwargs):
    df = st.data_editor(
        st.session_state[key],
        column_config=columns,
        use_container_width=True,
        hide_index=True,
        **kwargs,
    )
    st.session_state[key] = df
    return df


def _brand_columns():
    return {
        "name": st.column_config.TextColumn("Brand", disabled=True),
        "translated_name": st.column_config.TextColumn("Translated", disabled=True),
        "mentions": st.column_config.NumberColumn("Mentions", disabled=True),
        "action": st.column_config.SelectboxColumn("Action", options=ACTION_OPTIONS),
        "correct_name": st.column_config.TextColumn("Correct Name"),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _product_columns():
    return {
        "name": st.column_config.TextColumn("Product", disabled=True),
        "translated_name": st.column_config.TextColumn("Translated", disabled=True),
        "brand": st.column_config.TextColumn("Brand", disabled=True),
        "mentions": st.column_config.NumberColumn("Mentions", disabled=True),
        "action": st.column_config.SelectboxColumn("Action", options=ACTION_OPTIONS),
        "correct_name": st.column_config.TextColumn("Correct Name"),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _mapping_columns():
    return {
        "product_name": st.column_config.TextColumn("Product", disabled=True),
        "brand_name": st.column_config.TextColumn("Brand", disabled=True),
        "confidence": st.column_config.NumberColumn("Confidence", disabled=True),
        "source": st.column_config.TextColumn("Source", disabled=True),
        "action": st.column_config.SelectboxColumn("Action", options=MAPPING_ACTIONS),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _missing_mapping_columns(products, brands):
    return {
        "product_name": st.column_config.SelectboxColumn(
            "Product", options=_safe_options(products)
        ),
        "brand_name": st.column_config.SelectboxColumn(
            "Brand", options=_safe_options(brands)
        ),
        "action": st.column_config.SelectboxColumn(
            "Action", options=MISSING_MAPPING_ACTIONS
        ),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _translation_columns():
    return {
        "entity_type": st.column_config.SelectboxColumn(
            "Entity Type", options=ENTITY_OPTIONS
        ),
        "canonical_name": st.column_config.TextColumn("Canonical Name"),
        "language": st.column_config.SelectboxColumn("Language", options=LANG_OPTIONS),
        "current_translation_en": st.column_config.TextColumn("Current", disabled=True),
        "action": st.column_config.SelectboxColumn("Action", options=ACTION_OPTIONS),
        "override_text": st.column_config.TextColumn("Override"),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _ensure_state(context):
    if st.session_state.get(STATE_CONTEXT_KEY) == context["state_key"]:
        return
    st.session_state[STATE_CONTEXT_KEY] = context["state_key"]
    st.session_state[STATE_BRANDS] = _brand_df(context["candidates"])
    st.session_state[STATE_PRODUCTS] = _product_df(context["candidates"])
    st.session_state[STATE_MAPPINGS] = _mapping_df(context["candidates"])
    st.session_state[STATE_MISSING] = _missing_mapping_df(context["candidates"])
    st.session_state[STATE_TRANSLATIONS] = _translation_df(context["candidates"])


def _reset_state():
    for key in [
        STATE_CONTEXT_KEY,
        STATE_BRANDS,
        STATE_PRODUCTS,
        STATE_MAPPINGS,
        STATE_MISSING,
        STATE_TRANSLATIONS,
    ]:
        st.session_state.pop(key, None)


def _brand_df(candidates):
    rows = [
        {
            "name": item.get("name") or "",
            "translated_name": item.get("translated_name") or "",
            "mentions": item.get("mention_count", 0),
            "action": "",
            "correct_name": "",
            "reason": "",
        }
        for item in candidates.get("brands") or []
    ]
    return pd.DataFrame(rows)


def _product_df(candidates):
    rows = [
        {
            "name": item.get("name") or "",
            "translated_name": item.get("translated_name") or "",
            "brand": item.get("brand_name") or "",
            "mentions": item.get("mention_count", 0),
            "action": "",
            "correct_name": "",
            "reason": "",
        }
        for item in candidates.get("products") or []
    ]
    return pd.DataFrame(rows)


def _mapping_df(candidates):
    rows = [
        {
            "product_name": item.get("product_name") or "",
            "brand_name": item.get("brand_name") or "",
            "confidence": item.get("confidence", 0.0) or 0.0,
            "source": item.get("source") or "",
            "action": "",
            "reason": "",
        }
        for item in candidates.get("mappings") or []
    ]
    return pd.DataFrame(rows)


def _missing_mapping_df(candidates):
    rows = [
        {
            "product_name": item.get("product_name") or "",
            "brand_name": "",
            "action": "add",
            "reason": "",
        }
        for item in candidates.get("missing_mappings") or []
    ]
    return pd.DataFrame(
        rows or [{"product_name": "", "brand_name": "", "action": "add", "reason": ""}]
    )


def _translation_df(candidates):
    rows = [
        {
            "entity_type": item.get("entity_type") or "",
            "canonical_name": item.get("canonical_name") or "",
            "language": "en",
            "current_translation_en": item.get("current_translation_en") or "",
            "action": "",
            "override_text": "",
            "reason": "",
        }
        for item in candidates.get("translations") or []
    ]
    rows.append(
        {
            "entity_type": "",
            "canonical_name": "",
            "language": "en",
            "current_translation_en": "",
            "action": "",
            "override_text": "",
            "reason": "",
        }
    )
    return pd.DataFrame(rows)


def _product_options(candidates):
    products = candidates.get("products") or []
    missing = candidates.get("missing_mappings") or []
    return _unique(
        [p.get("name") for p in products] + [m.get("product_name") for m in missing]
    )


def _brand_options(vertical_brands):
    items = vertical_brands or []
    names = [b.get("original_name") or b.get("display_name") for b in items]
    return _unique(names)


def _unique(values):
    return sorted({(v or "").strip() for v in values if (v or "").strip()})


def _safe_options(items):
    return items if items else [""]


def _rows(key):
    df = st.session_state.get(key)
    return df.to_dict(orient="records") if df is not None else []


def _fetch_verticals():
    return _fetch_json("/api/v1/verticals") or []


def _fetch_vertical_brands(vertical_id: int):
    return _fetch_json(f"/api/v1/verticals/{vertical_id}/brands") or []


def _fetch_knowledge_verticals():
    return _fetch_json("/api/v1/knowledge/verticals") or []


def _fetch_candidates(vertical_id: int):
    return _fetch_json(
        "/api/v1/feedback/candidates", params={"vertical_id": vertical_id}
    )


def _api_url(path):
    return f"http://localhost:{settings.api_port}{path}"


def _fetch_json(path, params=None):
    try:
        response = httpx.get(_api_url(path), params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Request failed: {exc}")
        return None


def _post_json(path, payload):
    try:
        response = httpx.post(_api_url(path), json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Submit failed: {exc}")
        return None
