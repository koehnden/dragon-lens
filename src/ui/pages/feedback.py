import httpx
import pandas as pd
import streamlit as st

from config import settings
from ui.feedback_payload import build_feedback_payload

ACTION_OPTIONS = ["", "valid", "wrong"]
MAPPING_ACTIONS = ["", "wrong"]
MISSING_MAPPING_ACTIONS = ["", "add"]
ENTITY_OPTIONS = ["brand", "product"]
LANG_OPTIONS = ["en", "zh"]

STATE_RUN_ID = "feedback_run_id"
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
    _ensure_state(context["run"]["id"], context["entities"])
    _render_form(context)


def _context():
    vertical_id = _vertical_context()
    if not vertical_id:
        return None
    run = _run_context(vertical_id)
    if not run:
        return None
    entities = _run_entities(run["id"])
    if not entities:
        return None
    return _context_dict(vertical_id, run, entities)


def _context_dict(vertical_id, run, entities):
    return {
        "vertical_id": vertical_id,
        "run": run,
        "entities": entities,
        "knowledge_verticals": _fetch_knowledge_verticals(),
    }


def _vertical_context():
    verticals = _fetch_verticals()
    if not verticals:
        st.info("No verticals found. Create a tracking job first.")
        return None
    return _select_vertical(verticals)


def _run_context(vertical_id):
    models = _fetch_models(vertical_id)
    if not models:
        st.info("No completed runs for this vertical.")
        return None
    model = _select_model(models)
    runs = _fetch_runs(vertical_id, model)
    return _select_run(runs)


def _render_form(context):
    _run_summary(context["run"], context["entities"])
    form_state = _feedback_form(context)
    _handle_submit(context, form_state)


def _run_summary(run, entities):
    st.caption(f"Run {run['id']} | {run['model_name']} | {run['run_time']}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Brands", len(entities.get("brands", [])))
    col2.metric("Products", len(entities.get("products", [])))
    col3.metric("Mappings", len(entities.get("mappings", [])))


def _feedback_form(context):
    with st.form("feedback_form"):
        canonical = _canonical_vertical_input(context["knowledge_verticals"])
        _brands_section()
        _products_section()
        _mapping_section()
        _missing_mapping_section(context["entities"])
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
    payload = _payload_from_state(context, form_state["canonical"])
    response = _post_json("/api/v1/feedback/submit", payload)
    _submit_result(response)


def _payload_from_state(context, canonical):
    return build_feedback_payload(
        context["run"]["id"], context["vertical_id"], canonical,
        _rows(STATE_BRANDS), _rows(STATE_PRODUCTS), _rows(STATE_MAPPINGS),
        _rows(STATE_MISSING), _rows(STATE_TRANSLATIONS),
    )


def _canonical_vertical_input(knowledge_verticals):
    options = _canonical_options(knowledge_verticals)
    choice = st.selectbox("Canonical Vertical", options)
    if choice == "Create new":
        name = st.text_input("New Canonical Vertical")
        return {"is_new": True, "name": name.strip()}
    return _canonical_existing(knowledge_verticals, choice)


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


def _brands_section():
    st.subheader("Brands")
    return _edit_table(STATE_BRANDS, _brand_columns())


def _products_section():
    st.subheader("Products")
    return _edit_table(STATE_PRODUCTS, _product_columns())


def _mapping_section():
    st.subheader("Current Mappings")
    return _edit_table(STATE_MAPPINGS, _mapping_columns())


def _missing_mapping_section(entities):
    st.subheader("Missing Mappings")
    columns = _missing_mapping_columns(_product_options(entities), _brand_options(entities))
    return _edit_table(STATE_MISSING, columns, num_rows="dynamic")


def _translation_section():
    st.subheader("Translation Overrides")
    return _edit_table(STATE_TRANSLATIONS, _translation_columns(), num_rows="dynamic")


def _edit_table(key, columns, **kwargs):
    df = st.data_editor(st.session_state[key], column_config=columns, use_container_width=True, hide_index=True, **kwargs)
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
        "product_name": st.column_config.SelectboxColumn("Product", options=_safe_options(products)),
        "brand_name": st.column_config.SelectboxColumn("Brand", options=_safe_options(brands)),
        "action": st.column_config.SelectboxColumn("Action", options=MISSING_MAPPING_ACTIONS),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _translation_columns():
    return {
        "entity_type": st.column_config.SelectboxColumn("Entity Type", options=ENTITY_OPTIONS),
        "canonical_name": st.column_config.TextColumn("Canonical Name"),
        "language": st.column_config.SelectboxColumn("Language", options=LANG_OPTIONS),
        "override_text": st.column_config.TextColumn("Override"),
        "reason": st.column_config.TextColumn("Reason"),
    }


def _ensure_state(run_id, entities):
    if st.session_state.get(STATE_RUN_ID) == run_id:
        return
    st.session_state[STATE_RUN_ID] = run_id
    st.session_state[STATE_BRANDS] = _brand_df(entities)
    st.session_state[STATE_PRODUCTS] = _product_df(entities)
    st.session_state[STATE_MAPPINGS] = _mapping_df(entities)
    st.session_state[STATE_MISSING] = _missing_mapping_df()
    st.session_state[STATE_TRANSLATIONS] = _translation_df()


def _brand_df(entities):
    rows = [{
        "name": b.get("original_name") or b.get("brand_name", ""),
        "translated_name": b.get("translated_name") or "",
        "mentions": b.get("mention_count", 0),
        "action": "",
        "correct_name": "",
        "reason": "",
    } for b in entities.get("brands", [])]
    return pd.DataFrame(rows)


def _product_df(entities):
    rows = [{
        "name": p.get("original_name") or p.get("product_name", ""),
        "translated_name": p.get("translated_name") or "",
        "brand": p.get("brand_name") or "",
        "mentions": p.get("mention_count", 0),
        "action": "", "correct_name": "", "reason": "",
    } for p in entities.get("products", [])]
    return pd.DataFrame(rows)


def _mapping_df(entities):
    brands = _brand_lookup(entities)
    products = _product_lookup(entities)
    rows = [_mapping_row(m, products, brands) for m in entities.get("mappings", [])]
    return pd.DataFrame(rows)


def _mapping_row(mapping, products, brands):
    return {
        "product_name": products.get(mapping.get("product_id"), mapping.get("product_name", "")),
        "brand_name": brands.get(mapping.get("brand_id"), mapping.get("brand_name", "")),
        "confidence": mapping.get("confidence", 0.0),
        "source": mapping.get("source") or "",
        "action": "",
        "reason": "",
    }


def _missing_mapping_df():
    return pd.DataFrame([{"product_name": "", "brand_name": "", "action": "add", "reason": ""}])


def _translation_df():
    return pd.DataFrame([{"entity_type": "", "canonical_name": "", "language": "", "override_text": "", "reason": ""}])


def _brand_lookup(entities):
    return {b.get("brand_id"): b.get("original_name") or b.get("brand_name", "") for b in entities.get("brands", [])}


def _product_lookup(entities):
    return {p.get("product_id"): p.get("original_name") or p.get("product_name", "") for p in entities.get("products", [])}


def _product_options(entities):
    return [p.get("original_name") or p.get("product_name", "") for p in entities.get("products", [])]


def _brand_options(entities):
    return [b.get("original_name") or b.get("brand_name", "") for b in entities.get("brands", [])]


def _safe_options(items):
    return items if items else [""]


def _rows(key):
    df = st.session_state.get(key)
    return df.to_dict(orient="records") if df is not None else []


def _select_vertical(verticals):
    options = {v["name"]: v["id"] for v in verticals}
    name = st.selectbox("Vertical", list(options.keys()))
    return options.get(name)


def _select_model(models):
    return st.selectbox("Model", ["All"] + models)


def _select_run(runs):
    if not runs:
        return None
    options = {_run_label(r): r for r in runs}
    label = st.selectbox("Run", list(options.keys()))
    return options.get(label)


def _run_label(run):
    return f'{run["id"]} | {run["model_name"]} | {run["run_time"]}'


def _fetch_verticals():
    return _fetch_json("/api/v1/verticals") or []


def _fetch_knowledge_verticals():
    return _fetch_json("/api/v1/knowledge/verticals") or []


def _fetch_models(vertical_id):
    return _fetch_json(f"/api/v1/verticals/{vertical_id}/models") or []


def _fetch_runs(vertical_id, model_name):
    params = {"vertical_id": vertical_id}
    if model_name != "All":
        params["model_name"] = model_name
    runs = _fetch_json("/api/v1/tracking/runs", params=params)
    return _completed_runs(runs or [])


def _completed_runs(runs):
    completed = [run for run in runs if run.get("status") == "completed"]
    if not completed:
        st.info("No completed runs for this selection.")
    return completed


def _run_entities(run_id):
    return _fetch_json(f"/api/v1/tracking/runs/{run_id}/entities")


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


def _submit_result(data):
    if not data:
        return
    st.success("Feedback submitted.")
    st.write(data.get("applied") or {})
