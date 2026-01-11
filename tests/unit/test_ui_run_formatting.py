from ui.utils.run_formatting import format_run_option_label


def test_format_run_option_label_uses_run_time_date_prefix():
    label = format_run_option_label({"id": 12, "run_time": "2025-01-02T03:04:05Z"})
    assert label == "Run 12 - 2025-01-02"


def test_format_run_option_label_falls_back_to_created_at():
    label = format_run_option_label({"id": 7, "created_at": "2024-12-31T00:00:00"})
    assert label == "Run 7 - 2024-12-31"


def test_format_run_option_label_handles_missing_date():
    label = format_run_option_label({"id": 1})
    assert label == "Run 1 - unknown"

