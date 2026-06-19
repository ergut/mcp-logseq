# TLS Serving + Insecure-Bind Guardrail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `mcp-logseq --transport http` serve directly over TLS (so the bearer token and all content are encrypted on the wire), and refuse to bind a non-loopback interface over plain HTTP unless the operator explicitly opts in — so that publishing this tool does not hand downstream users a silent footgun.

**Architecture:** The HTTP transport already runs the MCP server through uvicorn (`run_http` in `src/mcp_logseq/transport/http.py`). uvicorn supports TLS natively via `ssl_certfile`/`ssl_keyfile`, so native TLS is a thin pass-through of two new CLI flags. Independently, a small validation step in the CLI entry point (`src/mcp_logseq/__init__.py`) classifies the bind host as loopback-or-not and refuses an unencrypted non-loopback bind unless `--insecure` is given. Both changes are additive and keep today's default (stdio, or plain HTTP on `127.0.0.1`) byte-for-byte unchanged. A TLS-terminating reverse proxy (e.g. Caddy) remains the recommended production path and is documented, not coded.

**Tech Stack:** Python, argparse, uvicorn (`ssl_certfile`/`ssl_keyfile`), existing Starlette/MCP transport.

## Global Constraints

- English only — all code, comments, docs, commit messages in English.
- Loopback bind default (`--host 127.0.0.1`) is unchanged; never default to `0.0.0.0`.
- `uvicorn` stays a lazy import inside `run_http` (the stdio path must not import it).
- Backward compatibility: existing `run_http(host, port, auth_token, read_only=False)` callers and the stdio path must keep working; new parameters default to "off" (`tls_cert=None`, `tls_key=None`, `insecure=False`) so current behavior is identical.
- No new runtime dependencies — uvicorn already ships TLS support via its `standard`/stdlib `ssl` path.
- Tests run with `LOGSEQ_API_TOKEN=test-token` in the environment (the suite imports `tools.py`, which raises at import without it). For the full suite also run `uv sync --extra vector` first.

---

## What ALREADY exists (reuse, do NOT rebuild)

Confirmed in the current tree:

- `src/mcp_logseq/__init__.py`: `parse_args(argv=None)` (argparse with `--transport`/`--host`/`--port`/`--read-only`) and `main()` which, on the http path, requires `MCP_HTTP_AUTH_TOKEN` then calls `http.run_http(args.host, args.port, token, read_only=args.read_only)`.
- `src/mcp_logseq/transport/http.py`: `run_http(host, port, auth_token, read_only=False)` → `uvicorn.run(create_asgi_app(...), host=host, port=port)` with uvicorn imported lazily.
- `tests/unit/test_cli.py`: existing CLI tests (parse_args defaults, http-without-token SystemExit, run_http call-through via monkeypatch). Mirror these patterns — do NOT introduce a new test style.

This plan only adds flags, a validation helper, and a uvicorn pass-through. It does not touch the ASGI app, auth middleware, or ACL layer.

---

## File Structure

- Modify: `src/mcp_logseq/transport/http.py` — `run_http` accepts `tls_cert`/`tls_key`, passes `ssl_certfile`/`ssl_keyfile` to `uvicorn.run`.
- Modify: `src/mcp_logseq/__init__.py` — add `--tls-cert`/`--tls-key`/`--insecure` to `parse_args`; add a testable `_validate_http_options(args)` helper; call it and thread TLS into `run_http` from `main()`.
- Modify: `tests/unit/test_cli.py` — extend with TLS pass-through, both-or-neither, and bind-guardrail tests.
- Modify: `README.md` — TLS section (native flags + reverse-proxy), and an explicit "encrypt anything past loopback" warning.

---

## Resolved Decisions

- **[DECIDE-A] TLS mechanism — RESOLVED: native uvicorn `ssl_certfile`/`ssl_keyfile`, plus documented reverse-proxy option.** Native TLS makes the tool self-sufficient for host-internal/self-signed encryption; a reverse proxy (Caddy, automatic Let's Encrypt) is the recommended internet-facing path and is documented in Task 3, not coded. *Tasks 1 & 3.*
- **[DECIDE-B] Insecure-bind posture — RESOLVED: explicit `--insecure` opt-in (refuse, do not merely warn).** Binding a non-loopback host over plain HTTP raises `SystemExit` unless `--insecure` is passed. A hard refuse-with-override beats a silent warning (warnings scroll past in service logs) and beats a blanket refusal (which would break the legitimate "plain HTTP behind a TLS proxy on a private interface" setup — the operator passes `--insecure` consciously there). Loopback bind over plain HTTP needs no opt-in. TLS-configured bind on any host needs no opt-in. *Task 2.* (Veto-able: if you prefer a loud warning over a hard refuse, that is the only knob to flip.)
- **[DECIDE-C] Loopback classification — RESOLVED: host in `{"127.0.0.1", "::1", "localhost"}` is loopback; everything else is "exposed".** This is a deliberately simple, conservative set: an operator who binds `127.0.0.2` (still loopback range) is treated as exposed and must pass TLS or `--insecure` — erring toward asking for explicit intent rather than guessing. Documented as such. *Task 2.*

---

## Task 1: Native TLS pass-through (`--tls-cert` / `--tls-key`)

**Files:**
- Modify: `src/mcp_logseq/transport/http.py`
- Modify: `src/mcp_logseq/__init__.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: existing `create_asgi_app(auth_token, read_only=False)`.
- Produces:
  - `run_http(host: str, port: int, auth_token: str, read_only: bool = False, tls_cert: str | None = None, tls_key: str | None = None) -> None`
  - `parse_args` namespace gains `tls_cert: str | None` and `tls_key: str | None` (default `None`).
  - `_validate_http_options(args) -> None` in `__init__.py` (raises `SystemExit` on bad combos). Task 2 extends this same function; Task 1 only implements the TLS-pair rule.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli.py`)

```python
def test_parse_args_tls_flags_default_none():
    args = parse_args(["--transport", "http"])
    assert args.tls_cert is None
    assert args.tls_key is None


def test_parse_args_tls_flags_parsed():
    args = parse_args(
        ["--transport", "http", "--tls-cert", "/c.pem", "--tls-key", "/k.pem"]
    )
    assert args.tls_cert == "/c.pem"
    assert args.tls_key == "/k.pem"


def test_validate_http_options_requires_both_tls_files(monkeypatch):
    from mcp_logseq import _validate_http_options

    args = parse_args(["--transport", "http", "--tls-cert", "/c.pem"])
    with pytest.raises(SystemExit):
        _validate_http_options(args)


def test_run_http_passes_ssl_to_uvicorn(monkeypatch):
    import mcp_logseq.transport.http as http_mod

    calls = {}

    def fake_uvicorn_run(app, **kwargs):
        calls.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)
    http_mod.run_http(
        "127.0.0.1", 12320, "tok", tls_cert="/c.pem", tls_key="/k.pem"
    )
    assert calls["ssl_certfile"] == "/c.pem"
    assert calls["ssl_keyfile"] == "/k.pem"


def test_run_http_no_tls_passes_none(monkeypatch):
    import mcp_logseq.transport.http as http_mod

    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(kw))
    http_mod.run_http("127.0.0.1", 12320, "tok")
    assert calls.get("ssl_certfile") is None
    assert calls.get("ssl_keyfile") is None
```

Ensure `import pytest` is present at the top of `tests/unit/test_cli.py` (add it if missing).

- [ ] **Step 2: Run to verify fail**

Run: `LOGSEQ_API_TOKEN=test-token uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL (`tls_cert` attribute missing / `_validate_http_options` not importable / `ssl_certfile` not passed).

- [ ] **Step 3: Add the TLS flags and validation helper** in `src/mcp_logseq/__init__.py`

In `parse_args`, add after the `--read-only` argument and before `return`:

```python
    p.add_argument(
        "--tls-cert",
        default=None,
        help="Path to a PEM TLS certificate. Enables HTTPS (requires --tls-key).",
    )
    p.add_argument(
        "--tls-key",
        default=None,
        help="Path to the PEM TLS private key (requires --tls-cert).",
    )
```

Add this module-level helper (place it above `main()`):

```python
def _validate_http_options(args) -> None:
    """Validate TLS options for the http transport. Raises SystemExit on misconfig.

    Task 2 extends this with the insecure-bind guardrail.
    """
    import os

    if (args.tls_cert is None) != (args.tls_key is None):
        raise SystemExit("--tls-cert and --tls-key must be provided together")
    if args.tls_cert is not None:
        for label, path in (("--tls-cert", args.tls_cert), ("--tls-key", args.tls_key)):
            if not os.path.isfile(path):
                raise SystemExit(f"{label} file not found: {path}")
```

- [ ] **Step 4: Thread TLS through `main()`** — update the http branch in `src/mcp_logseq/__init__.py`

```python
    else:
        token = os.environ.get("MCP_HTTP_AUTH_TOKEN")
        if not token:
            raise SystemExit("MCP_HTTP_AUTH_TOKEN is required for --transport http")
        _validate_http_options(args)
        from .transport import http

        http.run_http(
            args.host,
            args.port,
            token,
            read_only=args.read_only,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
        )
```

- [ ] **Step 5: Pass SSL to uvicorn** in `src/mcp_logseq/transport/http.py`

Replace `run_http` with:

```python
def run_http(
    host: str,
    port: int,
    auth_token: str,
    read_only: bool = False,
    tls_cert: str | None = None,
    tls_key: str | None = None,
) -> None:
    """Run the HTTP transport with uvicorn (imported lazily).

    When ``tls_cert``/``tls_key`` are provided, uvicorn serves over HTTPS.
    """
    import uvicorn

    uvicorn.run(
        create_asgi_app(auth_token, read_only=read_only),
        host=host,
        port=port,
        ssl_certfile=tls_cert,
        ssl_keyfile=tls_key,
    )
```

- [ ] **Step 6: Run to verify pass**

Run: `LOGSEQ_API_TOKEN=test-token uv run pytest tests/unit/test_cli.py -v`
Expected: PASS (all new tests). Then full suite: `LOGSEQ_API_TOKEN=test-token uv sync --extra vector && LOGSEQ_API_TOKEN=test-token uv run pytest --tb=short` — Expected: PASS, no regression.

- [ ] **Step 7: Commit**

```bash
git add src/mcp_logseq/transport/http.py src/mcp_logseq/__init__.py tests/unit/test_cli.py
git commit -m "feat(transport): native TLS serving via --tls-cert/--tls-key"
```

(Use the trailer `Co-Authored-By: Claude <noreply@anthropic.com>`.)

---

## Task 2: Insecure-bind guardrail (`--insecure` opt-in)

**Files:**
- Modify: `src/mcp_logseq/__init__.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `_validate_http_options(args)` from Task 1.
- Produces: `parse_args` namespace gains `insecure: bool` (default `False`); `_validate_http_options` additionally raises `SystemExit` when binding a non-loopback host over plain HTTP without `--insecure`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli.py`)

```python
def test_parse_args_insecure_default_false():
    args = parse_args(["--transport", "http"])
    assert args.insecure is False


def test_validate_refuses_non_loopback_plain_http():
    from mcp_logseq import _validate_http_options

    args = parse_args(["--transport", "http", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        _validate_http_options(args)


def test_validate_allows_non_loopback_with_insecure():
    from mcp_logseq import _validate_http_options

    args = parse_args(["--transport", "http", "--host", "0.0.0.0", "--insecure"])
    _validate_http_options(args)  # must not raise


def test_validate_allows_non_loopback_with_tls(tmp_path):
    from mcp_logseq import _validate_http_options

    cert = tmp_path / "c.pem"; cert.write_text("x")
    key = tmp_path / "k.pem"; key.write_text("x")
    args = parse_args(
        ["--transport", "http", "--host", "10.0.0.5",
         "--tls-cert", str(cert), "--tls-key", str(key)]
    )
    _validate_http_options(args)  # must not raise


def test_validate_allows_loopback_plain_http():
    from mcp_logseq import _validate_http_options

    for host in ("127.0.0.1", "localhost", "::1"):
        args = parse_args(["--transport", "http", "--host", host])
        _validate_http_options(args)  # must not raise
```

- [ ] **Step 2: Run to verify fail**

Run: `LOGSEQ_API_TOKEN=test-token uv run pytest tests/unit/test_cli.py -k "insecure or non_loopback or loopback_plain" -v`
Expected: FAIL (`insecure` attribute missing / no guardrail raise).

- [ ] **Step 3: Add `--insecure` flag** in `parse_args` (after `--tls-key`)

```python
    p.add_argument(
        "--insecure",
        action="store_true",
        help=(
            "Allow binding a non-loopback host over plain HTTP. Without TLS the "
            "bearer token and all content travel unencrypted — only use on a "
            "trusted network or behind a TLS-terminating reverse proxy."
        ),
    )
```

- [ ] **Step 4: Extend `_validate_http_options`** — add the guardrail after the TLS-file checks from Task 1

```python
    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
    tls_enabled = args.tls_cert is not None
    if args.host not in _LOOPBACK_HOSTS and not tls_enabled and not args.insecure:
        raise SystemExit(
            f"Refusing to bind {args.host} over plain HTTP: the bearer token and "
            f"all content would travel unencrypted. Either provide --tls-cert/"
            f"--tls-key, put a TLS-terminating reverse proxy in front and bind a "
            f"loopback address, or pass --insecure to override (not recommended "
            f"outside a trusted network)."
        )
```

Define `_LOOPBACK_HOSTS` at module level (top of `__init__.py`) rather than inside the function if you prefer; either is acceptable as long as the helper reads it. Keep the whole helper in one place.

- [ ] **Step 5: Run to verify pass**

Run: `LOGSEQ_API_TOKEN=test-token uv run pytest tests/unit/test_cli.py -v`
Expected: PASS. Then full suite: `LOGSEQ_API_TOKEN=test-token uv run pytest --tb=short` — Expected: PASS, no regression. Also smoke-test the default still works: `LOGSEQ_API_TOKEN=test-token MCP_HTTP_AUTH_TOKEN=x` is NOT needed here — instead assert via the tests above; do not start a real server.

- [ ] **Step 6: Commit**

```bash
git add src/mcp_logseq/__init__.py tests/unit/test_cli.py
git commit -m "feat(cli): refuse non-loopback plain-HTTP bind without --insecure"
```

(Use the `Co-Authored-By` trailer.)

---

## Task 3: Document TLS and the bind guardrail

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "TLS / encrypted serving" subsection** under the existing "Serving over HTTP" section. Read the current README first to match heading style and the existing profile examples. Document, accurately to the code in Tasks 1-2:

  - Native TLS: `mcp-logseq --transport http --port 12320 --tls-cert /path/cert.pem --tls-key /path/key.pem`. Both flags are required together. Mention obtaining a cert (`mkcert`/self-signed for host-internal, Let's Encrypt for public DNS).
  - The bind guardrail: binding a non-loopback host (anything other than `127.0.0.1`/`localhost`/`::1`) over plain HTTP is refused; the operator must supply TLS or pass `--insecure` to consciously accept an unencrypted bind (only sane behind a TLS-terminating proxy on a trusted network).
  - Recommended production path: a reverse proxy (Caddy with automatic HTTPS) terminating TLS in front of a loopback-bound `mcp-logseq`. Show a minimal Caddy example:

````markdown
# Caddyfile — automatic HTTPS in front of a loopback-bound instance
logseq.example.com {
    reverse_proxy 127.0.0.1:12320
}
````

  - One explicit security sentence: the bearer token and all content are plaintext over plain HTTP, so anything past loopback must be encrypted (native TLS or a TLS proxy).

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: TLS serving, reverse-proxy guidance, insecure-bind guardrail"
```

(Use the `Co-Authored-By` trailer.)

---

## Backward Compatibility

- All new flags default to off; `parse_args([])` and the stdio path are unchanged.
- `run_http`'s new `tls_cert`/`tls_key` default to `None`, so `uvicorn.run(..., ssl_certfile=None, ssl_keyfile=None)` is exactly today's plain-HTTP behavior; existing callers pass nothing new.
- A plain `--transport http --port N` on the default loopback host still starts with no TLS and no opt-in required — only non-loopback binds change behavior.

## Self-Review Notes

- **Spec coverage:** native TLS (Task 1), insecure-bind guardrail (Task 2), docs incl. reverse proxy (Task 3). Covered.
- **Reuse over rebuild:** extends `run_http` and `parse_args`/`main`; no new transport, no ASGI/auth/ACL changes.
- **Name consistency:** `_validate_http_options(args)`, `run_http(..., tls_cert, tls_key)`, flags `--tls-cert`/`--tls-key`/`--insecure`, `_LOOPBACK_HOSTS` used identically across tasks.
- **No 0.0.0.0 default; loopback unchanged.** The guardrail makes an unencrypted exposed bind an explicit, conscious act.
- **[DECIDE-A/B/C]** pinned to their tasks; DECIDE-B is the only veto-able knob (hard-refuse vs warn).
