"""End-to-end HTTP serving + profile isolation (Task 7).

Acceptance coverage for the secure HTTP serving feature. A single profile is
used throughout: a ``Journal/*``-only allow-list (``Work/*`` denied) behind a
known bearer token.

Strategy note
-------------
Two layers are exercised:

* **AUTH** runs through the REAL stack: a context-manager ``TestClient`` over
  the actual Starlette app produced by ``create_asgi_app`` — i.e. through the
  genuine ``BearerAuthMiddleware`` and the mounted ``/mcp`` route. No token /
  wrong token must 401; the right token must pass the middleware (not 401).

* **ISOLATION** and **READ-ONLY** use *strategy B* (per the task brief). A full
  in-process MCP Streamable-HTTP handshake (initialize/initialized + SSE) is
  brittle to drive in-process and would mostly re-test the MCP SDK's wire
  protocol rather than this project's security contract. Instead we drive the
  EXACT handler registry the served app exposes — ``build_app(read_only=...)``
  returns ``(server, handlers)`` where ``handlers`` is the same dict the app's
  ``call_tool`` closure dispatches to — with the profile's ACL config active.
  This proves denied-namespace content never surfaces and that the read-only
  app's tool set omits genuine write tools, end-to-end through the served app
  object, without re-testing the SDK.
"""

from unittest.mock import Mock, patch

import pytest
from starlette.testclient import TestClient

from mcp_logseq.access import AccessConfig, AccessDenied
from mcp_logseq.transport.http import create_asgi_app
from mcp_logseq.server import build_app, _WRITE_TOOL_NAMES


TOKEN = "journal-profile-token"


def _journal_only_profile():
    """Activate the Journal-only ACL profile on the served handlers' config.

    ``include=['Journal']`` is a strict allow-list: only ``Journal`` and its
    children are reachable; ``Work/*`` (and every other namespace) is denied.
    """
    return patch(
        "mcp_logseq.access.get_access_config",
        return_value=AccessConfig(include_namespaces=["Journal"]),
    )


# ---------------------------------------------------------------------------
# Step 1 + Step 2: build the served app and assert auth through the real stack.
# ---------------------------------------------------------------------------


def test_no_token_is_rejected_through_real_middleware(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    with TestClient(create_asgi_app(auth_token=TOKEN)) as client:
        r = client.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
        )
    assert r.status_code == 401


def test_wrong_token_is_rejected_through_real_middleware(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    with TestClient(create_asgi_app(auth_token=TOKEN)) as client:
        r = client.post(
            "/mcp/",
            headers={"Authorization": "Bearer wrong-token"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert r.status_code == 401


def test_correct_token_passes_middleware(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    # Context-manager TestClient runs the lifespan so the MCP session task
    # group is initialized; /mcp/ avoids the 307 redirect.
    with TestClient(create_asgi_app(auth_token=TOKEN)) as client:
        r = client.post(
            "/mcp/",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    # The correct token cleared the middleware; whatever the MCP layer answers,
    # it must NOT be the auth rejection and must not be a post-auth crash.
    assert r.status_code != 401
    assert r.status_code < 500


# ---------------------------------------------------------------------------
# Step 3: isolation — denied (Work/*) content never surfaces; Journal/* does.
# Driven through the SAME handler registry the served app dispatches to.
# ---------------------------------------------------------------------------


def _served_handlers(read_only: bool = False) -> dict:
    """The exact handler registry the served HTTP app dispatches tool calls to."""
    _, handlers = build_app(read_only=read_only)
    return handlers


def test_get_page_content_denies_work_page(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    handlers = _served_handlers()
    with _journal_only_profile():
        with pytest.raises(AccessDenied):
            handlers["get_page_content"].run_tool({"page_name": "Work/secret-roadmap"})


def test_query_for_work_page_returns_nothing(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    fake = Mock()
    fake.query_dsl.return_value = [
        {"originalName": "Work/secret-roadmap"},
        {"originalName": "Work/salaries"},
    ]
    handlers = _served_handlers()
    with _journal_only_profile(), patch(
        "mcp_logseq.tools._make_api", return_value=fake
    ):
        out = handlers["query"].run_tool({"query": "(page-property x)"})[0].text
    assert "Work/" not in out
    assert "secret-roadmap" not in out
    assert "salaries" not in out


def test_search_excludes_work_pages_and_keeps_journal(monkeypatch):
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    fake = Mock()
    fake.list_pages.return_value = [
        {"originalName": "Work/secret-roadmap", "properties": {}},
        {"originalName": "Journal/2026-06-15", "properties": {}},
    ]
    handlers = _served_handlers()
    # The served search handler resolves blocked page names via the SAME helper
    # the live tool uses; assert Work/* is on the excluded list and Journal is not.
    handler = handlers["search"]
    with _journal_only_profile(), patch(
        "mcp_logseq.tools._make_api", return_value=fake
    ):
        # Signature: (api, exclude_tags, exclude_namespaces, include_namespaces).
        # Returns lowercased names of blocked pages.
        excluded = handler._build_excluded_page_names(
            fake, [], [], ["Journal"]
        )
    assert "work/secret-roadmap" in excluded
    assert "journal/2026-06-15" not in excluded


def test_journal_page_is_reachable(monkeypatch):
    """A Journal/* page passes the pre-flight guard and returns its content."""
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    fake = Mock()
    fake.get_page_content.return_value = {
        "page": {"originalName": "Journal/2026-06-15", "properties": {}},
        "blocks": [{"content": "Today I shipped the HTTP transport"}],
    }
    handlers = _served_handlers()
    with _journal_only_profile(), patch(
        "mcp_logseq.tools._make_api", return_value=fake
    ):
        out = handlers["get_page_content"].run_tool(
            {"page_name": "Journal/2026-06-15", "format": "text"}
        )[0].text
    assert "Today I shipped the HTTP transport" in out


def test_vector_search_registered_and_isolated(monkeypatch, tmp_path):
    """When vector is configured, the served app registers vector_search, and
    the namespace filter that tool relies on drops Work/* while keeping
    Journal/*. If the vector extra is unavailable, skip cleanly."""
    pytest.importorskip("mcp_logseq.vector.index")
    import json

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "logseq_graph_path": str(tmp_path),
                "vector": {
                    "enabled": True,
                    "db_path": str(tmp_path / "db"),
                    "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
                },
            }
        )
    )
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")

    handlers = _served_handlers()
    assert "vector_search" in handlers, "vector_search must be exposed by served app"

    # The served vector tool filters its results through this helper. Under the
    # Journal-only profile, a Work/* hit physically present in a shared index
    # must be dropped; Journal/* survives.
    from mcp_logseq.vector.index import _filter_results_by_namespace

    class R:
        def __init__(self, page):
            self.page = page

    results = [R("Work/secret-roadmap"), R("Journal/2026-06-15")]
    kept = _filter_results_by_namespace(results, include=["Journal"], exclude=[])
    pages = [r.page for r in kept]
    assert pages == ["Journal/2026-06-15"]


# ---------------------------------------------------------------------------
# Step 4: writes — denied namespace raises; read-only app drops write tools.
# ---------------------------------------------------------------------------


def test_write_to_work_page_is_denied(monkeypatch):
    """On a writable served app, a write targeting Work/* raises AccessDenied."""
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    handlers = _served_handlers(read_only=False)
    assert "create_page" in handlers  # writable instance
    with _journal_only_profile():
        with pytest.raises(AccessDenied):
            handlers["create_page"].run_tool(
                {"title": "Work/new-plan", "content": "secret"}
            )
        with pytest.raises(AccessDenied):
            handlers["update_page"].run_tool(
                {"page_name": "Work/secret-roadmap", "content": "x"}
            )


def test_read_only_served_app_omits_write_tools(monkeypatch):
    """The read-only served app exposes NO genuine write tool; read tools stay."""
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")
    handlers = _served_handlers(read_only=True)
    for name in _WRITE_TOOL_NAMES:
        assert name not in handlers, f"{name} must be absent under read_only"
    for name in [
        "list_pages",
        "get_page_content",
        "search",
        "query",
        "get_pages_from_namespace",
        "get_page_backlinks",
    ]:
        assert name in handlers, f"read tool {name} must remain under read_only"


def test_read_only_keeps_sync_vector_when_configured(monkeypatch, tmp_path):
    """sync_vector_db is not a genuine write tool; it survives read-only when
    vector is configured for the served app."""
    pytest.importorskip("mcp_logseq.vector.index")
    import json

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "logseq_graph_path": str(tmp_path),
                "vector": {
                    "enabled": True,
                    "db_path": str(tmp_path / "db"),
                    "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
                },
            }
        )
    )
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_API_TOKEN", "x")

    handlers = _served_handlers(read_only=True)
    for name in ["sync_vector_db", "vector_search", "vector_db_status"]:
        assert name in handlers, f"{name} must remain under read_only"
    for name in _WRITE_TOOL_NAMES:
        assert name not in handlers
