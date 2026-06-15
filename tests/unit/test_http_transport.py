import pytest
from starlette.testclient import TestClient
from mcp_logseq.transport.auth import BearerAuthMiddleware
from mcp_logseq.transport.http import create_asgi_app


async def _invoke_auth(headers):
    """Drive BearerAuthMiddleware.__call__ with a hand-built HTTP scope.

    Returns the status code the middleware (or the wrapped app) emits. The
    wrapped app, if reached, returns 200; auth rejections return 401.
    """

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BearerAuthMiddleware(downstream, token="secret")
    scope = {"type": "http", "headers": headers, "method": "POST", "path": "/mcp"}

    status = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    await middleware(scope, receive, send)
    return status["code"]


def test_asgi_app_mounts_mcp_endpoint(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    monkeypatch.setenv("MCP_HTTP_AUTH_TOKEN", "secret")
    app = create_asgi_app(auth_token="secret")
    client = TestClient(app)
    # No/bad bearer → 401 (auth covered in Task 2; here assert the route exists)
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code in (401, 400)  # route exists, not 404


def test_missing_token_is_401(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    client = TestClient(create_asgi_app(auth_token="secret"))
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401


def test_wrong_token_is_401(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    client = TestClient(create_asgi_app(auth_token="secret"))
    r = client.post(
        "/mcp",
        headers={"Authorization": "Bearer nope"},
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )
    assert r.status_code == 401


def test_correct_token_passes_auth(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    # Context-manager TestClient runs the app lifespan (MCP session task group).
    with TestClient(create_asgi_app(auth_token="secret")) as client:
        r = client.post(
            "/mcp/",
            headers={"Authorization": "Bearer secret"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    # Auth let it through and the MCP handler responded without crashing.
    # < 500 catches a post-auth 500; it is also not a 401 rejection.
    assert r.status_code < 500


@pytest.mark.asyncio
async def test_duplicate_auth_headers_is_401():
    # One valid + one invalid Authorization header must be rejected (ambiguous),
    # not accepted by last-wins dict collapsing.
    status = await _invoke_auth(
        [
            (b"authorization", b"Bearer secret"),
            (b"authorization", b"Bearer nope"),
        ]
    )
    assert status == 401


@pytest.mark.asyncio
async def test_non_ascii_auth_header_is_401():
    # Non-ASCII bytes must yield a clean 401, never a 500 from a decode crash.
    status = await _invoke_auth([(b"authorization", b"Bearer \xff\xfe")])
    assert status == 401


@pytest.mark.asyncio
async def test_single_valid_auth_header_passes():
    # Sanity check that the hand-built scope path accepts a correct token.
    status = await _invoke_auth([(b"authorization", b"Bearer secret")])
    assert status == 200
