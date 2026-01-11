def _as_date_prefix(value: object | None) -> str:
    if value is None:
        return "unknown"
    text = str(value)
    if not text:
        return "unknown"
    return text[:10]


def format_run_option_label(run: dict) -> str:
    run_id = run.get("id", "unknown")
    date_value = run.get("run_time") or run.get("created_at") or run.get("completed_at")
    return f"Run {run_id} - {_as_date_prefix(date_value)}"

