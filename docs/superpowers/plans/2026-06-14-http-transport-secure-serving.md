# HTTP/SSE Transport + Secure Multi-Profile Serving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `mcp-logseq` run as a networked HTTP/SSE service on the host so a sandboxed client (e.g. an agent running inside a container) can reach it without any filesystem mount or direct Logseq-API access — making the existing namespace/tag access control a real security boundary.

**Architecture:** The server currently runs stdio-only and is therefore co-located with its client. Its access-control layer (include/exclude namespaces, exclude tags, per-config-file "profiles") already exists and is fail-closed. The missing piece is a network transport: add an HTTP/SSE (Streamable HTTP) entry mode with bearer-token auth, bound to a configurable interface, so the server can sit on the host owning the raw data (vector DB + Logseq HTTP API on loopback) while the client gets only filtered tool results over HTTP. Multiple single-profile instances (one config file + one port each) provide per-profile isolation with zero new multi-tenant code.

**Tech Stack:** Python, MCP Python SDK (`mcp` — Streamable HTTP server transport), Starlette + uvicorn (ASGI host), existing `mcp.server.Server` app, existing `config.py` ACL loaders.

---

## Consumer Model (context, not in scope)

The client is a **sandboxed agent** — assume it runs in a container or other locked-down environment and must never touch raw data. In the target deployment the agent has **no** bind mounts of the vault or vector DB and **no** network route to the Logseq HTTP API; its only Logseq channel is this server's HTTP endpoint. All access control therefore has to be enforced **server-side, before any bytes leave the process**. Wiring the client/container/network is a separate concern in the consuming application and is **out of scope for this plan** — this plan only makes the server securely servable over the network.

---

## What ALREADY Exists (do NOT rebuild)

Confirmed in the current tree — the developer should reuse, not reimplement:

- **Per-profile config** via `LOGSEQ_CONFIG_FILE` → `src/mcp_logseq/config.py`: `load_include_namespaces()`, `load_exclude_namespaces()`, `load_exclude_tags()`, plus the `vector` block. A "profile" is one config file. Each process loads exactly one.
- **ACL enforcement, fail-closed**, in `src/mcp_logseq/tools.py`: module-level `_include_namespaces` / `_exclude_namespaces` / `_exclude_tags` (lines 59-61), `_is_namespace_blocked`, `_is_page_blocked`, `_enforce_namespace_access` (raises `AccessDenied`), `_enforce_block_namespace_access` (fail-closed when a block's page can't be resolved). Search/query result filtering at `tools.py:1241, 1382, 1508`.
- **Vector-search filtering** in `src/mcp_logseq/vector/index.py:230` using the same namespace globals.
- **stdio transport** in `src/mcp_logseq/server.py:83-89` (`stdio_server()`), entry `mcp-logseq = "mcp_logseq:main"` → `server.main()`.

Because the ACL globals are loaded at import time and live per-process, **running N instances with N config files needs no refactor of the ACL layer.** The work is transport + auth + a completeness audit of the network surface.

---

## Scope (in / out)

**In scope (vector + normal search era):**
- HTTP/SSE transport with bearer auth and configurable bind address, selectable without breaking stdio.
- A documented "one instance per profile" run pattern.
- A security audit ensuring **every content-returning tool** enforces the ACL over the new HTTP surface, and a policy for write tools.

**Out of scope (now):**
- Vault/raw-file browsing for the client (the user will use the Logseq web app for read-only browsing).
- Single-page "fetch + KB formatting" as a distinct product feature (formatting lives in the consumer).
- Any consumer/container/network wiring.

---

## Open Decisions (resolve before the dependent task)

- **[DECIDE-A] Transport flavor.** Streamable HTTP (current MCP recommendation) vs legacy SSE. Default to **Streamable HTTP**; only fall back to SSE if the pinned `mcp` version lacks it. *Dependent: Task 1.*
- **[DECIDE-B] Auth token source.** Read the endpoint bearer token from an env var (`MCP_HTTP_AUTH_TOKEN`) and/or a config-file key. Default: env var, required when `--transport http`. *Dependent: Task 2.*
- **[DECIDE-C] Write tools over HTTP.** Either (a) keep write tools exposed but ensure each is gated by `_enforce_namespace_access` before mutating, or (b) add a per-instance `--read-only` flag that unregisters write tools entirely. Recommended: implement **both** — (a) is the correctness floor, (b) is the simplest hard guarantee per profile. *Dependent: Task 5.*

---

## File Structure

- Create: `src/mcp_logseq/transport/__init__.py`
- Create: `src/mcp_logseq/transport/http.py` — ASGI app wrapping the existing `Server`, bearer-auth middleware, uvicorn runner.
- Modify: `src/mcp_logseq/server.py` — factor tool registration into an importable `build_app()` so both stdio and HTTP reuse it; add transport dispatch.
- Modify: `src/mcp_logseq/__init__.py` — `main()` parses `--transport {stdio,http}`, `--host`, `--port`.
- Modify: `pyproject.toml` — bump `mcp` to a version with Streamable HTTP; add `starlette`, `uvicorn`; (optional) `serve` console alias.
- Create: `tests/unit/test_http_transport.py`
- Create: `tests/integration/test_http_serving.py`
- Modify: `tests/unit/test_namespace_access.py` — extend to assert the guard holds on every content-returning tool (Task 4).
- Modify: `README.md` — document host-serving, the per-profile multi-instance pattern, and the security model.

---

## Phase 1 — HTTP transport

### Task 1: Factor `build_app()` and add the HTTP ASGI module

**Files:**
- Modify: `src/mcp_logseq/server.py`
- Create: `src/mcp_logseq/transport/__init__.py` (empty)
- Create: `src/mcp_logseq/transport/http.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_http_transport.py`

- [ ] **Step 1: Resolve [DECIDE-A].** Confirm the pinned `mcp` version exposes Streamable HTTP (`from mcp.server.streamable_http_manager import StreamableHTTPSessionManager` or equivalent). Record the exact import path here. If absent, bump `mcp` in `pyproject.toml` and re-sync (`uv sync`).

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_http_transport.py
import pytest
from starlette.testclient import TestClient
from mcp_logseq.transport.http import create_asgi_app

def test_asgi_app_mounts_mcp_endpoint(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    monkeypatch.setenv("MCP_HTTP_AUTH_TOKEN", "secret")
    app = create_asgi_app(auth_token="secret")
    client = TestClient(app)
    # No/!bad bearer → 401 (auth covered in Task 2; here assert the route exists)
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code in (401, 400)  # route exists, not 404
```

- [ ] **Step 3: Run to verify fail** — Run: `uv run pytest tests/unit/test_http_transport.py -v` — Expected: FAIL (module `transport.http` missing).

- [ ] **Step 4: Refactor `server.py`** so tool registration is reusable:

```python
# server.py — extract everything that registers tool handlers into:
def build_app() -> Server:
    app = Server("mcp-logseq")
    _register_all_tool_handlers(app)   # the existing add_tool_handler(...) calls
    return app
```

Keep `main()`'s stdio path calling `build_app()` so behavior is unchanged.

- [ ] **Step 5: Implement `transport/http.py`**

```python
# src/mcp_logseq/transport/http.py
import contextlib
from collections.abc import AsyncIterator
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # confirm in Step 1
from ..server import build_app

def create_asgi_app(auth_token: str) -> Starlette:
    app = build_app()
    manager = StreamableHTTPSessionManager(app=app)

    async def handle(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    asgi = Starlette(routes=[Mount("/mcp", app=handle)], lifespan=lifespan)
    from .auth import BearerAuthMiddleware     # added in Task 2
    asgi.add_middleware(BearerAuthMiddleware, token=auth_token)
    return asgi

def run_http(host: str, port: int, auth_token: str) -> None:
    import uvicorn
    uvicorn.run(create_asgi_app(auth_token), host=host, port=port)
```

- [ ] **Step 6: Add deps** to `pyproject.toml` (`starlette`, `uvicorn`, bumped `mcp`); `uv sync`.

- [ ] **Step 7: Run to verify pass** — Run: `uv run pytest tests/unit/test_http_transport.py -v` — Expected: PASS.

- [ ] **Step 8: Commit** — `git commit -m "feat(transport): HTTP/SSE ASGI app wrapping the MCP server"`

### Task 2: Bearer-token auth middleware

**Files:**
- Create: `src/mcp_logseq/transport/auth.py`
- Test: `tests/unit/test_http_transport.py` (extend)

- [ ] **Step 1: Resolve [DECIDE-B].** Confirm token source = `MCP_HTTP_AUTH_TOKEN` (required in http mode). Record here.

- [ ] **Step 2: Write the failing tests**

```python
def test_missing_token_is_401(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    client = TestClient(create_asgi_app(auth_token="secret"))
    r = client.post("/mcp", json={"jsonrpc":"2.0","id":1,"method":"ping"})
    assert r.status_code == 401

def test_wrong_token_is_401(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    client = TestClient(create_asgi_app(auth_token="secret"))
    r = client.post("/mcp", headers={"Authorization": "Bearer nope"},
                    json={"jsonrpc":"2.0","id":1,"method":"ping"})
    assert r.status_code == 401
```

- [ ] **Step 3: Run to verify fail** — Expected: FAIL (no auth module / 404).

- [ ] **Step 4: Implement `auth.py`**

```python
# src/mcp_logseq/transport/auth.py
import hmac
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        prefix = "Bearer "
        presented = auth[len(prefix):] if auth.startswith(prefix) else ""
        if not presented or not hmac.compare_digest(presented, self._token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
```

- [ ] **Step 5: Run to verify pass** — Expected: PASS (both 401 tests).

- [ ] **Step 6: Commit** — `git commit -m "feat(transport): bearer-token auth middleware for HTTP endpoint"`

### Task 3: `--transport` CLI dispatch + bind address

**Files:**
- Modify: `src/mcp_logseq/__init__.py`
- Modify: `pyproject.toml` (optional `serve` alias)
- Test: `tests/unit/test_cli.py` (create)

- [ ] **Step 1: Write the failing test** — `parse_args(["--transport","http","--host","127.0.0.1","--port","12320"])` returns a namespace with those values; default (no args) → `transport="stdio"`.

- [ ] **Step 2: Run to verify fail** — Expected: FAIL.

- [ ] **Step 3: Implement** an `argparse` layer in `__init__.py`:

```python
def main():
    import argparse, asyncio
    p = argparse.ArgumentParser(prog="mcp-logseq")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")   # loopback default; never 0.0.0.0
    p.add_argument("--port", type=int, default=12320)
    args = p.parse_args()
    if args.transport == "stdio":
        from . import server
        asyncio.run(server.main())
    else:
        import os
        token = os.environ.get("MCP_HTTP_AUTH_TOKEN")
        if not token:
            raise SystemExit("MCP_HTTP_AUTH_TOKEN is required for --transport http")
        from .transport.http import run_http
        run_http(args.host, args.port, token)
```

- [ ] **Step 4: Run to verify pass** — Expected: PASS. Also smoke-test stdio is unchanged: `echo '' | uv run mcp-logseq` still starts the stdio server.

- [ ] **Step 5: Commit** — `git commit -m "feat(cli): --transport http|stdio with loopback-default bind"`

---

## Phase 2 — Per-profile multi-instance

### Task 4 (audit): every content-returning tool enforces the ACL

This is the real security work: the HTTP surface exposes the **full tool set**, so any tool that can return page/block content — not just search — must enforce the namespace/tag guard. A client could otherwise name a denied page directly or run a DSL `query` that returns blocks from a denied namespace.

**Files:**
- Modify: `tests/unit/test_namespace_access.py`
- Modify: any tool handler in `src/mcp_logseq/tools.py` found to bypass the guard.

- [ ] **Step 1: Enumerate** every registered tool that returns block/page content (search, vector search, direct get-page/get-block, DSL `query`, backlinks, list-pages, namespace listings). Write the list into the test file as a checklist comment.

- [ ] **Step 2: Write failing tests** — with a profile that denies `Private/*`, assert each enumerated tool, when asked for or able to surface a `Private/*` page, returns nothing for it or raises `AccessDenied`. Example:

```python
def test_dsl_query_cannot_return_denied_namespace(denied_private_profile, api_stub):
    # api returns a Private/* block; tool must filter/deny it
    out = run_tool("query", {"query": "(page-tags)"})
    assert "Private/" not in serialize(out)

def test_direct_get_page_denied(denied_private_profile):
    with pytest.raises(AccessDenied):
        run_tool("get_page", {"name": "Private/Health"})
```

- [ ] **Step 3: Run to verify fail** — Expected: FAIL for any tool currently missing the guard.

- [ ] **Step 4: Add `_enforce_namespace_access` / `_is_page_blocked` filtering** to each bypassing tool (mirror the existing pattern at `tools.py:1241/1382/1508`). For DSL `query`, filter the returned block list by each block's owning page.

- [ ] **Step 5: Run to verify pass** — Expected: PASS for all enumerated tools.

- [ ] **Step 6: Commit** — `git commit -m "fix(acl): enforce namespace/tag guard on all content-returning tools"`

### Task 5: Write-tool policy (gated + optional read-only)

**Files:**
- Modify: `src/mcp_logseq/tools.py` (write handlers) and `src/mcp_logseq/__init__.py` / `server.py` (`--read-only`)
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Resolve [DECIDE-C].** Confirm both (a) gate writes and (b) `--read-only`.

- [ ] **Step 2: Write failing tests** — (a) `create_page`/`update_block`/`set_block_properties`/`insert_nested_block`/`delete_block` targeting `Private/*` raise `AccessDenied`; (b) with `--read-only`, write tools are absent from `list_tools()`.

- [ ] **Step 3: Run to verify fail** — Expected: FAIL.

- [ ] **Step 4: Implement** — call `_enforce_namespace_access(target_page)` (and `_enforce_block_namespace_access` for block-targeted writes) at the top of each write handler; add a `--read-only` flag threaded into `build_app()` that skips registering write handlers.

- [ ] **Step 5: Run to verify pass** — Expected: PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(acl): gate writes by namespace + per-instance --read-only"`

### Task 6: Document the per-profile run pattern

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Document that a "profile" = one config file, and you run one instance per profile on its own port, each with its own `MCP_HTTP_AUTH_TOKEN`:

````markdown
# Journal-only profile
LOGSEQ_CONFIG_FILE=~/.logseq/profiles/journal.json \
MCP_HTTP_AUTH_TOKEN=$JOURNAL_TOKEN \
mcp-logseq --transport http --port 12320

# Work-only profile (separate process, separate port, separate token)
LOGSEQ_CONFIG_FILE=~/.logseq/profiles/work.json \
MCP_HTTP_AUTH_TOKEN=$WORK_TOKEN \
mcp-logseq --transport http --port 12321
````

Note: each instance loads exactly one config, so namespace scoping is per-process. Bind to loopback (or a host-internal interface), never `0.0.0.0`.

- [ ] **Step 2: Commit** — `git commit -m "docs: per-profile HTTP serving and security model"`

---

## Phase 3 — Acceptance

### Task 7: End-to-end serving + isolation

**Files:**
- Create: `tests/integration/test_http_serving.py`

- [ ] **Step 1:** Start an in-process HTTP app with a `Journal/*`-only profile and a known token.
- [ ] **Step 2 (auth):** request with no/wrong token → 401; with the right token → MCP handshake succeeds.
- [ ] **Step 3 (isolation):** via the authenticated client, exercise search, vector search, and a direct get/query for a `Work/*` page → none surface `Work/*`; a `Journal/*` query returns results.
- [ ] **Step 4 (writes):** if not `--read-only`, a write to `Work/*` → `AccessDenied`; with `--read-only`, the write tool is not listed.
- [ ] **Step 5:** Run: `uv run pytest tests/integration/test_http_serving.py -v` — Expected: PASS. Record outcomes; only then mark serving complete.
- [ ] **Step 6: Commit** — `git commit -m "test(integration): end-to-end HTTP serving + profile isolation"`

---

## Backward Compatibility

- `--transport` defaults to `stdio`; existing stdio users (and the `mcp-logseq = "mcp_logseq:main"` entry) are unchanged. Task 3 Step 4 includes a stdio smoke test as the regression guard.
- All new behavior is opt-in via `--transport http`. No config migration; existing config files work as-is (they already define the profile/ACL).
- New deps (`starlette`, `uvicorn`) are runtime-only; the stdio path does not import them (import them lazily inside `run_http`).

---

## Self-Review Notes

- **Spec coverage:** transport (Task 1), auth (Task 2), CLI/bind (Task 3), full-surface ACL audit (Task 4), writes (Task 5), per-profile docs (Task 6), acceptance (Task 7). Covered.
- **Reuse over rebuild:** ACL and per-profile config already exist; Tasks 4–5 *audit and extend* the existing guard rather than introduce a new one.
- **No 0.0.0.0:** loopback default is stated in Task 3 and Task 6 — binding scope is part of the security contract.
- **Name consistency:** `build_app()`, `create_asgi_app(auth_token)`, `run_http(host, port, auth_token)`, `BearerAuthMiddleware(token=...)`, `MCP_HTTP_AUTH_TOKEN`, `--transport/--host/--port/--read-only` used identically across tasks.
- **[DECIDE-A/B/C]** are pinned to their dependent tasks.
```
