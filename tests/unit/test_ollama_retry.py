"""Unit tests for OllamaService retry logic, persistent client, and format param."""

import httpx
import pytest

from services.ollama import OllamaService


@pytest.fixture(autouse=True)
def _reset_shared_client():
    OllamaService._shared_client = None
    yield
    if OllamaService._shared_client and not OllamaService._shared_client.is_closed:
        OllamaService._shared_client = None


@pytest.fixture()
def ollama():
    return OllamaService()


class _FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response | Exception]):
        self._responses = list(responses)
        self.call_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok_response(content: str = '{"message":{"content":"ok"}}') -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


def _overload_response() -> httpx.Response:
    return httpx.Response(503, text="overloaded")


@pytest.mark.asyncio
async def test_call_succeeds_on_first_try(ollama, monkeypatch):
    transport = _FakeTransport([_ok_response("hello")])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))

    result = await ollama._call_ollama(model="test", prompt="hi")
    assert result == "hello"
    assert transport.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_read_timeout(ollama, monkeypatch):
    transport = _FakeTransport([
        httpx.ReadTimeout("timeout"),
        httpx.ReadTimeout("timeout"),
        _ok_response("recovered"),
    ])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr("services.ollama.settings.ollama_retry_base_delay", 0.01)

    result = await ollama._call_ollama(model="test", prompt="hi")
    assert result == "recovered"
    assert transport.call_count == 3


@pytest.mark.asyncio
async def test_retry_on_connect_error(ollama, monkeypatch):
    transport = _FakeTransport([
        httpx.ConnectError("refused"),
        _ok_response("back"),
    ])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr("services.ollama.settings.ollama_retry_base_delay", 0.01)

    result = await ollama._call_ollama(model="test", prompt="hi")
    assert result == "back"
    assert transport.call_count == 2


@pytest.mark.asyncio
async def test_exhausted_retries_raises(ollama, monkeypatch):
    transport = _FakeTransport([
        httpx.ReadTimeout("t1"),
        httpx.ReadTimeout("t2"),
        httpx.ReadTimeout("t3"),
    ])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr("services.ollama.settings.ollama_retry_base_delay", 0.01)

    with pytest.raises(httpx.ReadTimeout):
        await ollama._call_ollama(model="test", prompt="hi")
    assert transport.call_count == 3


@pytest.mark.asyncio
async def test_503_triggers_retry(ollama, monkeypatch):
    transport = _FakeTransport([
        _overload_response(),
        _ok_response("ok"),
    ])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr("services.ollama.settings.ollama_retry_base_delay", 0.01)

    result = await ollama._call_ollama(model="test", prompt="hi")
    assert result == "ok"
    assert transport.call_count == 2


@pytest.mark.asyncio
async def test_non_retryable_error_raises_immediately(ollama, monkeypatch):
    transport = _FakeTransport([
        httpx.Response(400, text="bad request"),
    ])
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))

    with pytest.raises(httpx.HTTPStatusError):
        await ollama._call_ollama(model="test", prompt="hi")
    assert transport.call_count == 1


@pytest.mark.asyncio
async def test_format_json_in_payload(ollama, monkeypatch):
    import json

    captured_payloads: list[dict] = []
    original_transport = httpx.AsyncBaseTransport()

    class _CapturingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured_payloads.append(body)
            return _ok_response()

    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=_CapturingTransport()))

    await ollama._call_ollama(model="test", prompt="hi", format="json")
    assert captured_payloads[0]["format"] == "json"

    captured_payloads.clear()
    await ollama._call_ollama(model="test", prompt="hi")
    assert "format" not in captured_payloads[0]


@pytest.mark.asyncio
async def test_keep_alive_in_payload(ollama, monkeypatch):
    import json

    class _CapturingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.last_payload: dict = {}

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.last_payload = json.loads(request.content)
            return _ok_response()

    transport = _CapturingTransport()
    monkeypatch.setattr(OllamaService, "_shared_client", httpx.AsyncClient(transport=transport))

    await ollama._call_ollama(model="test", prompt="hi")
    assert "keep_alive" in transport.last_payload


def test_shared_client_reused():
    c1 = OllamaService._get_client()
    c2 = OllamaService._get_client()
    assert c1 is c2
