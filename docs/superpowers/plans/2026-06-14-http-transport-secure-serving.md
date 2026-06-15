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

**Isolation model — decided: multi-instance, not multi-tenant.** A single shared process with a runtime `token → policy` lookup was considered and rejected: it would turn a hard OS-level wall into a soft in-process lookup, require refactoring every ACL check from module globals to request-scoped policy, and make a single bug a cross-profile leak. With multi-instance, the profile boundary *is* the process boundary — another profile's config is never even loaded — so the worst case is a profile leaking its own permitted data, never another's. Profiles are few and slow-changing (e.g. local-LLM / Claude / GPT tiers), so the ops cost of N processes is trivial against the isolation gain.

---

## Vector DB & Sync Model (multi-instance)

The vector DB is a single on-disk store shared by all reader instances. ACL controls operate on **two axes** — index-time (global, what the DB contains) vs query-time (per-instance, what a profile sees). **Do not conflate them:**

- **Index-time — `vector` block, the writer's single global policy.** `vector.exclude_tags` (exists) decides what is ever embedded/stored — use it for content no tier may ever vector-search (e.g. `#secret` raw credentials). Anything excluded here is gone for **every** profile and never embedded. *(An index-time **namespace** equivalent — `vector.include_namespaces` / `vector.exclude_namespaces` — is a separate, transport-independent feature tracked in [index-time namespace scoping](2026-06-15-index-time-namespace-scoping.md); it composes with this model but is out of scope for this plan.)*
- **Query-time — env per instance → `_exclude_tags` / `_include_namespaces` / `_exclude_namespaces`.** Decides which profile sees which already-stored content. This is the per-tier wall.

**Single writer, separated from readers (decided).** Exactly one dedicated process owns the DB — `logseq-sync --watch` (or `--once` under launchd/systemd/cron), guarded by the existing `sync.lock` ([bin/logseq_sync.py:45-60](../../../src/mcp_logseq/bin/logseq_sync.py#L45-L60)). It indexes with the **single fixed index policy** above. **No MCP instance triggers sync at all:** `sync_vector_db`'s handler no longer spawns a subprocess — it returns instructions to run `logseq-sync` externally (Task 5b). Since it is then inert (returns text, mutates nothing), `--read-only` does not special-case it. This makes "whose index policy wins" impossible: there is one writer with one policy, and all per-tier differentiation is query-time.

**Gap this exposes:** `vector_search` currently filters results by namespace only, **not** by `_exclude_tags` ([index.py:49-55](../../../src/mcp_logseq/vector/index.py#L49-L55)). On the shared DB that means a profile which should exclude `#keys` would still receive `#keys` pages over HTTP. Task 4 closes this (the data is available: chunks carry `tags`, surfaced as `SearchResult.tags`).

---

## Profile & Config Model (decided)

**Decision: one shared data/vector config file + per-instance policy via env vars — no separate sync config file, no new config-loading code.**

`db_path` and `embedder` are an irreducible shared truth: the writer and every reader must agree on them (an embedder mismatch raises, [sync.py:95-99](../../../src/mcp_logseq/vector/sync.py#L95-L99)). So they live in **one** file:

- **Shared `data.json`** (owned by the writer): `logseq_graph_path` + the `vector` block (`db_path`, `embedder`, index-time `exclude_tags` = never-store only, journal/chunk settings). `LOGSEQ_CONFIG_FILE` points here for the writer **and** every reader. Readers use it for `db_path`/`embedder` (open DB read-only + embed queries) and `graph_path` (informational staleness check — the *server* has graph access on the host; the sandboxed agent does not).
- **Per-reader policy via env** (one launchd/systemd unit each): `LOGSEQ_INCLUDE_NAMESPACES`, `LOGSEQ_EXCLUDE_NAMESPACES`, `LOGSEQ_EXCLUDE_TAGS` (query-time), `MCP_HTTP_AUTH_TOKEN`, `--port`, `--read-only`. This works because the ACL loaders already take **env over config file** ([config.py:122-127](../../../src/mcp_logseq/config.py#L122-L127)) — no merge mechanism needed.

A profile is therefore "the shared data file + a unit file's env block." Adding a tier = a new unit with a few env lines and a token; the data file and DB are untouched. (A profile that prefers file-based policy can still set the root-level ACL keys in its own config file — env is just the zero-duplication default.)

---

## Scope (in / out)

**In scope (vector + normal search era):**
- HTTP/SSE transport with bearer auth and configurable bind address, selectable without breaking stdio.
- A documented "one instance per profile" run pattern, plus a separate single-writer `logseq-sync` process that owns the shared vector DB.
- A security audit ensuring **every content-returning tool** enforces the ACL over the new HTTP surface (including the `vector_search` tag gap), and a policy for write tools and sync.

**Out of scope (now):**
- Vault/raw-file browsing for the client (the user will use the Logseq web app for read-only browsing).
- Single-page "fetch + KB formatting" as a distinct product feature (formatting lives in the consumer).
- Any consumer/container/network wiring.

---

## Resolved Decisions

- **[DECIDE-A] Transport flavor — RESOLVED: Streamable HTTP.** Current MCP recommendation. Fall back to legacy SSE only if the pinned `mcp` version lacks it (confirm in Task 1 Step 1). *Task 1.*
- **[DECIDE-B] Auth token source — RESOLVED: `MCP_HTTP_AUTH_TOKEN` env var,** required when `--transport http` (no config-file key). *Task 2.*
- **[DECIDE-C] Write tools over HTTP — RESOLVED: implement both, least-privilege posture.**
  - **Namespace gating on writes already exists** (PR #65) on every write tool: `create_page` ([tools.py:269](../../../src/mcp_logseq/tools.py#L269)), `delete_page` (607), `update_page` (701), block writes via `_enforce_block_namespace_access` (791/846/1918/2002), and `rename_page` checks **both** old and new name (1745-1746), which already closes the "temp page → rename into a blocked namespace" smuggling path. So Task 5 does **not** re-add namespace gating.
  - **New work in Task 5:** (b) a per-instance `--read-only` flag that unregisters all genuine write tools (create/update/delete/rename page+block). It does **not** touch `sync_vector_db` — that handler becomes an inert "run `logseq-sync` externally" stub on every instance (Task 5b), since the DB is owned by the separate writer. Read-only tiers run `--read-only`; only tiers that need to write run writable.
  - **Tag asymmetry on writes (recommended add):** write gating is namespace-only; reads block by tag OR namespace. A `#keys`-tagged page in an *allowed* namespace is therefore writable/deletable though unreadable. For integrity, extend `update_page`/`delete_page`/`update_block`/`delete_block`/`set_block_properties` to also deny tag-blocked targets (a fetch-then-`_is_page_excluded` check; new pages have no prior tags so `create_page` is exempt). Marked recommended — veto-able.

  *Task 5.*

---

## File Structure

- Create: `src/mcp_logseq/transport/__init__.py`
- Create: `src/mcp_logseq/transport/http.py` — ASGI app wrapping the existing `Server`, bearer-auth middleware, uvicorn runner.
- Modify: `src/mcp_logseq/server.py` — factor tool registration into an importable `build_app()` so both stdio and HTTP reuse it; add transport dispatch.
- Modify: `src/mcp_logseq/__init__.py` — `main()` parses `--transport {stdio,http}`, `--host`, `--port`, `--read-only`.
- Modify: `src/mcp_logseq/vector/index.py` — `vector_search` query-time tag filter (Task 4); `sync_vector_db` external-pointer stub (Task 5b).
- Modify: `pyproject.toml` — bump `mcp` to a version with Streamable HTTP; add `starlette`, `uvicorn`; (optional) `serve` console alias.
- Create: `tests/unit/test_http_transport.py`
- Create: `tests/integration/test_http_serving.py`
- Modify: `tests/unit/test_namespace_access.py` — extend to assert the guard holds on every content-returning tool, incl. the `vector_search` tag gap (Task 4) and `--read-only` (Task 5).
- Modify: `tests/unit/test_vector_tools.py` — `sync_vector_db` stub (Task 5b).
- Modify: `README.md` — document host-serving, the per-profile multi-instance pattern, the separate sync writer, and the security model.

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

- [ ] **Step 4: Implement `auth.py` as PURE ASGI middleware**

> **Do not use `starlette.middleware.base.BaseHTTPMiddleware`.** It buffers the
> response body and is known to break streaming / SSE responses — which
> Streamable HTTP relies on for server→client messages. A pure ASGI middleware
> passes the send channel straight through and does not interfere with streaming.

```python
# src/mcp_logseq/transport/auth.py
import hmac
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

class BearerAuthMiddleware:
    """Pure ASGI auth — streaming-safe (no BaseHTTPMiddleware buffering)."""
    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        prefix = "Bearer "
        presented = auth[len(prefix):] if auth.startswith(prefix) else ""
        if not presented or not hmac.compare_digest(presented, self._token):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self._app(scope, receive, send)
```

`asgi.add_middleware(BearerAuthMiddleware, token=auth_token)` still works — Starlette wraps any ASGI-callable class, not just `BaseHTTPMiddleware` subclasses.

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

- [ ] **Step 4b (vector tag gap — REQUIRED): apply `_exclude_tags` to `vector_search`.** Today `vector_search` filters results by namespace only ([index.py:49-55](../../../src/mcp_logseq/vector/index.py#L49-L55)); on the shared DB this leaks tag-blocked pages (e.g. `#keys`) to profiles that should not see them. Add a query-time tag filter mirroring `_filter_results_by_namespace`. The data is already on each result — no API call needed:

```python
# src/mcp_logseq/vector/index.py — import _exclude_tags alongside the namespace globals
def _filter_results_by_tags(results, exclude_tags):
    if not exclude_tags:
        return results
    return [r for r in results if not any(t in exclude_tags for t in (r.tags or []))]

# in run_tool, after the namespace filter:
results = _filter_results_by_namespace(results, _include_namespaces, _exclude_namespaces)
results = _filter_results_by_tags(results, _exclude_tags)
```

Add a failing test first: a profile with `LOGSEQ_EXCLUDE_TAGS=keys` must not surface a `#keys` chunk from `vector_search`, even though that chunk is physically in the shared DB.

- [ ] **Step 5: Run to verify pass** — Expected: PASS for all enumerated tools.

- [ ] **Step 6: Commit** — `git commit -m "fix(acl): enforce namespace/tag guard on all content-returning tools"`

### Task 5: Write-tool policy (`--read-only` + tag-on-write)

> **Namespace gating on writes already exists** (PR #65 — see Resolved Decisions [DECIDE-C] for the per-tool line map, including `rename_page`'s dual old/new check). Do NOT re-add it. This task adds the `--read-only` flag and (recommended) closes the write-side tag asymmetry.

**Files:**
- Modify: `src/mcp_logseq/__init__.py` / `src/mcp_logseq/server.py` (`--read-only` threaded into `build_app()`)
- Modify: `src/mcp_logseq/tools.py` (tag check on existing-page write handlers)
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Regression guard for existing write gating.** Add tests asserting `create_page`/`update_block`/`set_block_properties`/`insert_nested_block`/`delete_block`/`delete_page`/`update_page` targeting `Private/*` raise `AccessDenied`, and `rename_page` denies when *either* old or new name is in `Private/*`. These should PASS already — they pin the PR #65 behavior so the `--read-only` refactor can't regress it.

- [ ] **Step 2: Write failing tests for the new behavior** — (a) with `--read-only`, every genuine write tool (create/update/delete/rename page+block) is absent from `list_tools()` while read tools (incl. `vector_search`, `vector_db_status`, and the inert `sync_vector_db` stub) remain; (b) [recommended] `update_page`/`delete_page`/`update_block`/`delete_block`/`set_block_properties` on a page tagged `#keys` (in an allowed namespace) raise `AccessDenied`.

- [ ] **Step 3: Run to verify fail** — Expected: Step 1 PASS, Step 2 FAIL.

- [ ] **Step 4: Implement** — thread a `--read-only` flag into `build_app()` that skips registering the genuine write handlers (leave `sync_vector_db`, `vector_search`, `vector_db_status` registered). [Recommended] For the tag asymmetry, add a fetch-then-`_is_page_excluded` check to the existing-page write handlers (resolve the block's owning page for block writes); `create_page` is exempt (no prior tags).

- [ ] **Step 5: Run to verify pass** — Expected: PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(acl): per-instance --read-only + tag-on-write guard"`

### Task 5b: Make `sync_vector_db` an inert external-sync pointer

The DB is owned by the separate writer (see Vector DB & Sync Model), so no MCP instance should spawn a sync subprocess.

**Files:**
- Modify: `src/mcp_logseq/vector/index.py` (`SyncVectorDBToolHandler`)
- Test: `tests/unit/test_vector_tools.py`

- [ ] **Step 1: Write the failing test** — calling `sync_vector_db` returns text containing `logseq-sync` and does **not** invoke `subprocess.run` (patch it and assert not called).

- [ ] **Step 2: Implement** — replace `run_tool`'s subprocess call with a static message; update the tool description to say sync runs externally on the host that owns the DB:

```
Vector DB sync is not available via MCP. Run it on the host that owns the DB:
  logseq-sync --once      # incremental sync
  logseq-sync --watch     # continuous file watcher
  logseq-sync --rebuild   # drop and re-index everything
```

- [ ] **Step 3: Run to verify pass.** **Step 4: Commit** — `git commit -m "feat(vector): sync_vector_db points to external logseq-sync (single-writer)"`

### Task 6: Document the per-profile run pattern

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Document that a "profile" = one config file, and you run one instance per profile on its own port, each with its own `MCP_HTTP_AUTH_TOKEN`:

All instances share **one** data config file (`db_path`/`embedder`/`graph_path`); each profile is just an env block + token (see Profile & Config Model). `--read-only` is a **new** capability introduced by Task 5 — these examples lean on it:

````markdown
# "journal-assistant" — reads your diary and reflects back, but can never edit it.
# Whole-instance read-only: no write tools at all.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_INCLUDE_NAMESPACES=Journal \
MCP_HTTP_AUTH_TOKEN=$JOURNAL_TOKEN \
mcp-logseq --transport http --port 12320 --read-only

# "work" — full read/write within Work/, and explicitly no diary access.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_INCLUDE_NAMESPACES=Work \
LOGSEQ_EXCLUDE_NAMESPACES=Journal \
MCP_HTTP_AUTH_TOKEN=$WORK_TOKEN \
mcp-logseq --transport http --port 12321

# "personal" — broad read/write, but credentials stay invisible.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_EXCLUDE_TAGS=keys,secret \
MCP_HTTP_AUTH_TOKEN=$PERSONAL_TOKEN \
mcp-logseq --transport http --port 12322
````

The data file is identical across all three; the per-process env block *is* the profile. The diary use case maps cleanly to whole-instance `--read-only`: `journal-assistant` reads `Journal/` and answers but holds zero write tools, while `work` excludes `Journal/` entirely. Bind to loopback (or a host-internal interface), never `0.0.0.0`.

- [ ] **Step 2: Document the separate sync writer.** The vector DB is owned by **one** dedicated `logseq-sync` process, deployed outside every MCP instance. It indexes with the single global index policy (`vector.exclude_tags` = secrets only; optional index-time namespace scoping is a separate feature — see [its plan](2026-06-15-index-time-namespace-scoping.md)); per-tier differentiation is purely query-time on the reader instances. Show both deployment shapes:

````markdown
# Continuous writer (launchd / systemd unit), owns the DB — same shared data file:
LOGSEQ_CONFIG_FILE=~/.logseq/data.json logseq-sync --watch

# Or scheduled one-shot (cron / launchd StartInterval):
LOGSEQ_CONFIG_FILE=~/.logseq/data.json logseq-sync --once
````

The writer reads no ACL env — only the `vector` block and `graph_path` from `data.json`. Its `vector.exclude_tags` (never-store only) is the sole index-time policy. Reader profiles share the same `db_path` read-only and never run sync.

- [ ] **Step 3: Commit** — `git commit -m "docs: per-profile HTTP serving, separate sync writer, security model"`

## Phase 3 — Acceptance

### Task 7: End-to-end serving + isolation

**Files:**
- Create: `tests/integration/test_http_serving.py`

- [ ] **Step 1:** Start an in-process HTTP app with a `Journal/*`-only profile and a known token.
- [ ] **Step 2 (auth):** request with no/wrong token → 401; with the right token → MCP handshake succeeds.
- [ ] **Step 3 (isolation):** via the authenticated client, exercise search, vector search, and a direct get/query for a `Work/*` page → none surface `Work/*`; a `Journal/*` query returns results.
- [ ] **Step 4 (writes):** if not `--read-only`, a write to `Work/*` → `AccessDenied`; with `--read-only`, no write tool is listed (but `sync_vector_db` stub and read tools remain).
- [ ] **Step 5:** Run: `uv run pytest tests/integration/test_http_serving.py -v` — Expected: PASS. Record outcomes; only then mark serving complete.
- [ ] **Step 6: Commit** — `git commit -m "test(integration): end-to-end HTTP serving + profile isolation"`

---

## Backward Compatibility

- `--transport` defaults to `stdio`; existing stdio users (and the `mcp-logseq = "mcp_logseq:main"` entry) are unchanged. Task 3 Step 4 includes a stdio smoke test as the regression guard.
- All new behavior is opt-in via `--transport http`. No config migration; existing config files work as-is (they already define the profile/ACL).
- New deps (`starlette`, `uvicorn`) are runtime-only; the stdio path does not import them (import them lazily inside `run_http`).

---

## Self-Review Notes

- **Spec coverage:** transport (Task 1), auth (Task 2), CLI/bind (Task 3), full-surface ACL audit incl. `vector_search` tag gap (Task 4), `--read-only` + tag-on-write (Task 5), `sync_vector_db` external-pointer stub (Task 5b), per-profile + separate-writer docs (Task 6), acceptance (Task 7). Covered. Index-time namespace scoping is split into its own plan (transport-independent).
- **Reuse over rebuild:** ACL and per-profile config already exist; Tasks 4–5 *audit and extend* the existing guard rather than introduce a new one. **Namespace gating on writes is already complete** (PR #65, incl. `rename_page` dual-endpoint) — Task 5 adds only `--read-only` and the recommended tag-on-write check, not namespace gating.
- **Config model:** one shared data/vector config file (writer-owned) + per-reader policy via env (namespace/tags/token) — leverages existing env-over-file precedence, no merge code, no `db_path`/`embedder` drift.
- **Isolation:** multi-instance (process boundary), not multi-tenant (runtime lookup) — decided in What ALREADY Exists / Isolation model.
- **Sync ownership:** one dedicated writer process; reader instances are `--read-only` and never sync. The two tag controls (index-time `vector.exclude_tags` vs query-time `LOGSEQ_EXCLUDE_TAGS`) are kept distinct.
- **Streaming safety:** auth is pure ASGI middleware, not `BaseHTTPMiddleware` (which would break SSE).
- **No 0.0.0.0:** loopback default is stated in Task 3 and Task 6 — binding scope is part of the security contract.
- **Name consistency:** `build_app()`, `create_asgi_app(auth_token)`, `run_http(host, port, auth_token)`, `BearerAuthMiddleware(token=...)`, `MCP_HTTP_AUTH_TOKEN`, `--transport/--host/--port/--read-only` used identically across tasks.
- **[DECIDE-A/B/C]** are pinned to their dependent tasks.
```
