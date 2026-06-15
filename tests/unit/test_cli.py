"""Unit tests for the CLI argument parsing and transport dispatch."""

import pytest

import mcp_logseq
from mcp_logseq import parse_args


def test_parse_args_http_explicit():
    ns = parse_args(["--transport", "http", "--host", "127.0.0.1", "--port", "12320"])
    assert ns.transport == "http"
    assert ns.host == "127.0.0.1"
    assert ns.port == 12320


def test_parse_args_defaults():
    ns = parse_args([])
    assert ns.transport == "stdio"
    assert ns.host == "127.0.0.1"
    assert ns.port == 12320


def test_main_http_without_token_raises(monkeypatch):
    monkeypatch.delenv("MCP_HTTP_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(mcp_logseq, "parse_args", lambda argv=None: parse_args(["--transport", "http"]))

    # Guard: even if it got past the token check, don't actually bind.
    import mcp_logseq.transport.http as http_mod
    monkeypatch.setattr(http_mod, "run_http", lambda *a, **k: None)

    with pytest.raises(SystemExit):
        mcp_logseq.main()


def test_main_http_with_token_calls_run_http(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_AUTH_TOKEN", "secret-token")
    monkeypatch.setattr(
        mcp_logseq,
        "parse_args",
        lambda argv=None: parse_args(["--transport", "http", "--host", "127.0.0.1", "--port", "12320"]),
    )

    calls = []

    import mcp_logseq.transport.http as http_mod
    monkeypatch.setattr(http_mod, "run_http", lambda *a, **k: calls.append((a, k)))

    mcp_logseq.main()

    assert calls == [(("127.0.0.1", 12320, "secret-token"), {})]
