import pytest
from fastapi import FastAPI, Request
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from client_middleware.middleware import create_tracking_middleware, send_log


SEND_LOG = "client_middleware.middleware.send_log"

# Unit tests
class FakeRequest:
    def __init__(self, method="GET", url_path="/test", client_host="127.0.0.1"):
        self.method = method
        self.url = type("URL", (), {"path": url_path})()  # Simulating a URL object, dynamically create a new class
        self.client = type("Client", (), {"host": client_host})()


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.mark.asyncio
async def test_middleware_is_callable():
    middleware = create_tracking_middleware("fake_key")
    assert callable(middleware)


@pytest.mark.asyncio
async def test_middleware_logs(monkeypatch):
    called = {}

    async def mock_send_log(log, api_key):
        called['log'] = log
        called['api_key'] = api_key

    monkeypatch.setattr(SEND_LOG, mock_send_log)

    request = FakeRequest()
    response = FakeResponse()

    async def mock_call_next(req):
        return response

    middleware = create_tracking_middleware("fake_key")
    result = await middleware(request, mock_call_next)

    assert result.status_code == 200
    assert called['log']['method'] == "GET"
    assert called['log']['endpoint'] == "/test"
    assert called['api_key'] == "fake_key"
    assert "created_at" in called['log']
    assert isinstance(called['log']['process_time'], float)


@pytest.mark.asyncio
async def test_middleware_missing_client_info(monkeypatch):
    called = {}

    async def mock_send_log(log, api_key):
        called['log'] = log

    monkeypatch.setattr(SEND_LOG, mock_send_log)

    request = FakeRequest()
    request.client = None  # simulate missing client info
    response = FakeResponse()

    async def mock_call_next(req):
        return response

    middleware = create_tracking_middleware("dummy_key")
    await middleware(request, mock_call_next)

    assert called['log']['ip'] is None


@pytest.mark.asyncio
async def test_send_log_swallow_exception(monkeypatch):
    class FakeAsyncClient:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass

        async def post(self, *args, **kwargs):
            raise Exception("Network error")

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    # Should not raise even if network error occurs
    await send_log({"test": "data"}, "fake_key")


# Integration test
@pytest.fixture
def app():
    app = FastAPI()
    app.middleware("http")(create_tracking_middleware("test_key"))

    @app.get("/ping")
    async def ping():
        return {"message": "pong"}

    return app


@pytest.mark.asyncio
async def test_middleware_integration(app):
    with patch(SEND_LOG, new_callable=AsyncMock) as mock_send_log:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ping")

        assert response.status_code == 200
        mock_send_log.assert_awaited_once()

        log, api_key = mock_send_log.call_args.args
        assert log["method"] == "GET"
        assert log["endpoint"] == "/ping"
        assert api_key == "test_key"
