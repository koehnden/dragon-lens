def build_feedback_payload(run_id, vertical_id, canonical_vertical, brand_rows, product_rows, mapping_rows, missing_rows, translation_rows) -> dict:
    return {
        "run_id": run_id, "vertical_id": vertical_id, "canonical_vertical": canonical_vertical,
        "brand_feedback": build_brand_feedback(brand_rows),
        "product_feedback": build_product_feedback(product_rows),
        "mapping_feedback": build_mapping_feedback(mapping_rows, missing_rows),
        "translation_overrides": build_translation_overrides(translation_rows),
    }


def build_brand_feedback(rows: list[dict]) -> list[dict]:
    return _items(rows, _brand_item)


def build_product_feedback(rows: list[dict]) -> list[dict]:
    return _items(rows, _product_item)


def build_mapping_feedback(existing_rows: list[dict], missing_rows: list[dict]) -> list[dict]:
    return _items(existing_rows, _reject_mapping_item) + _items(missing_rows, _add_mapping_item)


def build_translation_overrides(rows: list[dict]) -> list[dict]:
    return _items(rows, _translation_item)


def _items(rows: list[dict], builder) -> list[dict]:
    items: list[dict] = []
    for row in rows:
        item = builder(row)
        if item:
            items.append(item)
    return items


def _brand_item(row: dict) -> dict | None:
    action = _action(row)
    name = _text(row, "name")
    if action == "valid" and name:
        return {"action": "validate", "name": name, "reason": _reason(row)}
    if action == "wrong":
        return _replace_item(row, name)
    return None


def _product_item(row: dict) -> dict | None:
    action = _action(row)
    name = _text(row, "name")
    if action == "valid" and name:
        return {"action": "validate", "name": name, "reason": _reason(row)}
    if action == "wrong":
        return _replace_item(row, name)
    return None


def _replace_item(row: dict, wrong_name: str) -> dict | None:
    correct_name = _text(row, "correct_name")
    if not wrong_name or not correct_name or wrong_name == correct_name:
        return None
    return {
        "action": "replace",
        "wrong_name": wrong_name,
        "correct_name": correct_name,
        "reason": _reason(row),
    }


def _reject_mapping_item(row: dict) -> dict | None:
    if _action(row) != "wrong":
        return None
    product_name = _text(row, "product_name")
    brand_name = _text(row, "brand_name")
    if not product_name or not brand_name:
        return None
    return {"action": "reject", "product_name": product_name, "brand_name": brand_name, "reason": _reason(row)}


def _add_mapping_item(row: dict) -> dict | None:
    if _action(row) != "add":
        return None
    product_name = _text(row, "product_name")
    brand_name = _text(row, "brand_name")
    if not product_name or not brand_name:
        return None
    return {"action": "add", "product_name": product_name, "brand_name": brand_name, "reason": _reason(row)}


def _translation_item(row: dict) -> dict | None:
    entity_type = _text(row, "entity_type")
    canonical_name = _text(row, "canonical_name")
    language = _text(row, "language")
    override_text = _text(row, "override_text")
    if not all([entity_type, canonical_name, language, override_text]):
        return None
    return {"entity_type": entity_type, "canonical_name": canonical_name, "language": language, "override_text": override_text, "reason": _reason(row)}


def _action(row: dict) -> str:
    return _text(row, "action").lower()


def _text(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _reason(row: dict) -> str | None:
    value = _text(row, "reason")
    return value or None
