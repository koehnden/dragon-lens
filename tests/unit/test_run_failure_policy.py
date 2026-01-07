from config import settings


def test_should_fail_run_thresholds(monkeypatch):
    from workers.tasks import _should_fail_run

    monkeypatch.setattr(settings, "fail_if_failed_prompts_gt", 5)
    monkeypatch.setattr(settings, "fail_if_failed_rate_gt", 0.2)

    assert _should_fail_run([{"ok": True, "prompt_id": 1}]) is False
    assert _should_fail_run([{"ok": False, "prompt_id": 1}]) is True

    results = [{"ok": False, "prompt_id": i} for i in range(6)] + [{"ok": True, "prompt_id": 99}]
    assert _should_fail_run(results) is True

    results = [{"ok": False, "prompt_id": i} for i in range(5)] + [{"ok": True, "prompt_id": i} for i in range(5, 25)]
    assert _should_fail_run(results) is False

    results = [{"ok": False, "prompt_id": i} for i in range(4)] + [{"ok": True, "prompt_id": i} for i in range(4, 10)]
    assert _should_fail_run(results) is True
