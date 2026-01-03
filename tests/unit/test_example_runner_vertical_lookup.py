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

