from types import SimpleNamespace

import pytest


def test_check_existing_vertical_finds_by_exact_name(monkeypatch):
    from scripts import run_example_with_reuse as runner

    monkeypatch.setattr(runner, "settings", SimpleNamespace(api_port=8000))

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return [
                {"id": 1, "name": "SUV Cars"},
                {"id": 2, "name": "Diapers"},
                {"id": 3, "name": "Hiking Shoes"},
            ]

    monkeypatch.setattr(runner.requests, "get", lambda *args, **kwargs: FakeResponse())

    assert runner.check_existing_vertical("Hiking Shoes") == 3
    assert runner.check_existing_vertical("Diapers") == 2
    assert runner.check_existing_vertical("Missing") is None


def test_check_existing_vertical_returns_none_on_request_error(monkeypatch):
    from scripts import run_example_with_reuse as runner

    monkeypatch.setattr(runner, "settings", SimpleNamespace(api_port=8000))

    def boom(*args, **kwargs):
        raise runner.requests.RequestException("fail")

    monkeypatch.setattr(runner.requests, "get", boom)

    assert runner.check_existing_vertical("SUV Cars") is None


def test_parse_provider_and_model_uses_refreshed_visibility_models():
    from scripts import run_example_with_reuse as runner

    assert runner.parse_provider_and_model("kimi-k2") == ("kimi", "kimi-k2.5")
    assert runner.parse_provider_and_model("kimi-k2-or") == ("openrouter", "moonshotai/kimi-k2.5")
    assert runner.parse_provider_and_model("bytedance-seed") == ("openrouter", "bytedance-seed/seed-2.0-lite")
    assert runner.parse_provider_and_model("baidu-ernie") == ("openrouter", "baidu/ernie-4.5-21b-a3b")
    assert runner.parse_provider_and_model("qwen-72b") == ("openrouter", "qwen/qwen3.5-plus-02-15")
    assert runner.parse_provider_and_model("minimax-m2") == ("openrouter", "minimax/minimax-m2.5")
