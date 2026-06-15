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
