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

    assert calls == [
        (
            ("127.0.0.1", 12320, "secret-token"),
            {"read_only": False, "tls_cert": None, "tls_key": None},
        )
    ]


def test_main_http_read_only_threaded(monkeypatch):
    monkeypatch.setenv("MCP_HTTP_AUTH_TOKEN", "secret-token")
    monkeypatch.setattr(
        mcp_logseq,
        "parse_args",
        lambda argv=None: parse_args(
            ["--transport", "http", "--port", "12320", "--read-only"]
        ),
    )

    calls = []

    import mcp_logseq.transport.http as http_mod
    monkeypatch.setattr(http_mod, "run_http", lambda *a, **k: calls.append((a, k)))

    mcp_logseq.main()

    assert calls == [
        (
            ("127.0.0.1", 12320, "secret-token"),
            {"read_only": True, "tls_cert": None, "tls_key": None},
        )
    ]


def test_parse_args_tls_flags_default_none():
    args = parse_args(["--transport", "http"])
    assert args.tls_cert is None
    assert args.tls_key is None


def test_parse_args_tls_flags_parsed():
    args = parse_args(["--transport", "http", "--tls-cert", "/c.pem", "--tls-key", "/k.pem"])
    assert args.tls_cert == "/c.pem"
    assert args.tls_key == "/k.pem"


def test_validate_http_options_requires_both_tls_files():
    from mcp_logseq import _validate_http_options
    args = parse_args(["--transport", "http", "--tls-cert", "/c.pem"])
    with pytest.raises(SystemExit):
        _validate_http_options(args)


def test_validate_http_options_missing_cert_file(tmp_path):
    from mcp_logseq import _validate_http_options
    key = tmp_path / "k.pem"; key.write_text("x")
    args = parse_args(["--transport", "http", "--tls-cert", str(tmp_path / "nope.pem"), "--tls-key", str(key)])
    with pytest.raises(SystemExit):
        _validate_http_options(args)


def test_run_http_passes_ssl_to_uvicorn(monkeypatch):
    import mcp_logseq.transport.http as http_mod
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(kw))
    http_mod.run_http("127.0.0.1", 12320, "tok", tls_cert="/c.pem", tls_key="/k.pem")
    assert calls["ssl_certfile"] == "/c.pem"
    assert calls["ssl_keyfile"] == "/k.pem"


def test_run_http_no_tls_passes_none(monkeypatch):
    import mcp_logseq.transport.http as http_mod
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(kw))
    http_mod.run_http("127.0.0.1", 12320, "tok")
    assert calls.get("ssl_certfile") is None
    assert calls.get("ssl_keyfile") is None
