import pytest
from starlette.testclient import TestClient
from mcp_logseq.transport.http import create_asgi_app


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
    # Auth let it through; MCP session semantics decide the rest (not 401).
    assert r.status_code != 401
