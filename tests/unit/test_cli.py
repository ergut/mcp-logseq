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


def test_parse_args_invalid_transport_exits():
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--transport", "bogus"])
    # argparse exits with code 2 on an invalid choice.
    assert excinfo.value.code == 2


def test_main_http_without_token_raises(monkeypatch):
    monkeypatch.delenv("MCP_HTTP_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(mcp_logseq, "parse_args", lambda argv=None: parse_args(["--transport", "http"]))

    # Record any call: SystemExit must fire BEFORE run_http is reached, so the
    # recorder must stay empty. If the token guard is ever removed, this test
    # fails loudly instead of silently passing.
    calls = []
    import mcp_logseq.transport.http as http_mod
    monkeypatch.setattr(http_mod, "run_http", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(SystemExit):
        mcp_logseq.main()

    assert calls == [], "run_http must not be called when the token is missing"


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
