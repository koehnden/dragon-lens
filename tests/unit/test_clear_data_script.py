from scripts.clear_data import _reset_runs_sql


def test_reset_runs_sql_uses_enum_names_by_default():
    sql = _reset_runs_sql("name")
    assert "status = 'PENDING'" in sql
    assert "IN ('COMPLETED', 'FAILED', 'IN_PROGRESS')" in sql


def test_reset_runs_sql_uses_enum_values_when_requested():
    sql = _reset_runs_sql("value")
    assert "status = 'pending'" in sql
    assert "lower(status)" in sql
