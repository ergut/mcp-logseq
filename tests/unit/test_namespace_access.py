"""Tests for namespace-based access control."""

import json
import pytest
from unittest.mock import patch, Mock

from mcp_logseq.config import (
    load_include_namespaces,
    load_exclude_namespaces,
    load_exclude_tags,
)


# --- load_include_namespaces / load_exclude_namespaces ---

def test_include_empty_when_nothing_set(monkeypatch):
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_include_namespaces() == []


def test_include_reads_from_env(monkeypatch):
    monkeypatch.setenv("LOGSEQ_INCLUDE_NAMESPACES", "work, projects")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_include_namespaces() == ["work", "projects"]


def test_exclude_reads_from_env(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_NAMESPACES", "finance,personal")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_namespaces() == ["finance", "personal"]


def test_include_env_takes_priority_over_config(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"include_namespaces": ["from-file"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_INCLUDE_NAMESPACES", "from-env")
    assert load_include_namespaces() == ["from-env"]


def test_include_reads_from_config_list(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"include_namespaces": ["work", "projects"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == ["work", "projects"]


def test_exclude_reads_from_config_comma_string(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_namespaces": "finance, personal"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_NAMESPACES", raising=False)
    assert load_exclude_namespaces() == ["finance", "personal"]


def test_namespace_empty_when_config_missing_key(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"logseq_graph_path": "/x"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    monkeypatch.delenv("LOGSEQ_EXCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == []
    assert load_exclude_namespaces() == []


def test_namespace_empty_when_config_malformed(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("not json{{{")
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == []


def test_exclude_tags_still_works_after_refactor(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", "private, secret")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_tags() == ["private", "secret"]


# --- _namespace_matches / _is_namespace_blocked / _is_page_blocked ---

from mcp_logseq.namespace import namespace_matches as _namespace_matches
from mcp_logseq.tools import (
    _is_namespace_blocked,
    _is_page_blocked,
    AccessDenied,
)


def test_namespace_matches_exact():
    assert _namespace_matches("work", "work") is True


def test_namespace_matches_child():
    assert _namespace_matches("work/projects/q3", "work") is True


def test_namespace_matches_rejects_prefix_lookalike():
    assert _namespace_matches("workshop", "work") is False


def test_namespace_matches_case_insensitive():
    assert _namespace_matches("Work/Projects", "work") is True


def test_namespace_matches_trailing_slash_in_rule():
    assert _namespace_matches("work/x", "work/") is True


def test_blocked_when_excluded():
    assert _is_namespace_blocked("finance/q3", [], ["finance"]) is True


def test_exclude_wins_over_include():
    assert _is_namespace_blocked("work/secret/x", ["work"], ["work/secret"]) is True


def test_allowed_when_in_include():
    assert _is_namespace_blocked("work/projects", ["work"], []) is False


def test_strict_allowlist_blocks_non_matching():
    assert _is_namespace_blocked("personal/diary", ["work"], []) is True


def test_strict_allowlist_blocks_top_level_unnamespaced_page():
    assert _is_namespace_blocked("Fikirler", ["work"], []) is True


def test_no_rules_never_blocks():
    assert _is_namespace_blocked("anything/here", [], []) is False


def test_is_page_blocked_by_tag(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", ["private"]), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", []):
        page = {"properties": {"tags": ["private"]}}
        assert _is_page_blocked(page, "work/x") is True


def test_is_page_blocked_by_namespace(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", []), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", ["finance"]):
        page = {"properties": {"tags": []}}
        assert _is_page_blocked(page, "finance/q3") is True


def test_is_page_blocked_false_when_clear(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", ["private"]), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", ["finance"]):
        page = {"properties": {"tags": ["notes"]}}
        assert _is_page_blocked(page, "work/x") is False


from mcp_logseq.tools import (
    GetPageContentToolHandler,
    GetPageBacklinksToolHandler,
    GetPagesFromNamespaceToolHandler,
    GetPagesTreeFromNamespaceToolHandler,
    CreatePageToolHandler,
    UpdatePageToolHandler,
    DeletePageToolHandler,
    RenamePageToolHandler,
)


def _ns(include=None, exclude=None):
    """Patch namespace module config for a test."""
    return patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=include or [],
        _exclude_namespaces=exclude or [],
        _exclude_tags=[],
    )


def test_get_page_content_denies_excluded_namespace():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            GetPageContentToolHandler().run_tool({"page_name": "finance/q3"})


def test_get_page_content_denies_outside_allowlist():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPageContentToolHandler().run_tool({"page_name": "personal/diary"})


def test_get_page_backlinks_denies():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            GetPageBacklinksToolHandler().run_tool({"page_name": "finance/q3"})


def test_get_pages_from_namespace_denies():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPagesFromNamespaceToolHandler().run_tool({"namespace": "finance"})


def test_get_pages_tree_from_namespace_denies():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPagesTreeFromNamespaceToolHandler().run_tool({"namespace": "finance"})


def test_create_page_denies_excluded_namespace():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            CreatePageToolHandler().run_tool({"title": "finance/new", "content": "x"})


def test_update_page_denies_outside_allowlist():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            UpdatePageToolHandler().run_tool({"page_name": "personal/x", "content": "y"})


def test_delete_page_denies():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            DeletePageToolHandler().run_tool({"page_name": "finance/q3"})


def test_rename_page_denies_source():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool({"old_name": "personal/x", "new_name": "work/x"})


def test_rename_page_denies_target():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool({"old_name": "work/x", "new_name": "personal/x"})


from mcp_logseq.tools import (
    GetBlockToolHandler,
    UpdateBlockToolHandler,
    DeleteBlockToolHandler,
    InsertNestedBlockToolHandler,
    SetBlockPropertiesToolHandler,
)


def _api_with_block_page(page_name):
    """Mock _make_api so get_block_page_name returns a fixed page."""
    fake = Mock()
    fake.get_block_page_name.return_value = page_name
    return patch("mcp_logseq.tools._make_api", return_value=fake)


def test_get_block_denies_when_page_excluded():
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"):
        with pytest.raises(AccessDenied):
            GetBlockToolHandler().run_tool({"block_uuid": "u1"})


def test_update_block_denies_outside_allowlist():
    with _ns(include=["work"]), _api_with_block_page("personal/x"):
        with pytest.raises(AccessDenied):
            UpdateBlockToolHandler().run_tool({"block_uuid": "u2", "content": "c"})


def test_delete_block_denies():
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"):
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u3"})


def test_insert_nested_block_denies():
    with _ns(include=["work"]), _api_with_block_page("personal/x"):
        with pytest.raises(AccessDenied):
            InsertNestedBlockToolHandler().run_tool(
                {"parent_block_uuid": "u4", "content": "c"}
            )


def test_block_denied_when_page_unresolvable_and_rules_set():
    with _ns(include=["work"]), _api_with_block_page(None):
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u5"})


def test_block_allowed_when_no_rules():
    fake = Mock()
    fake.get_block_page_name.return_value = None
    fake.delete_block.return_value = {"ok": True}
    with _ns(), patch("mcp_logseq.tools._make_api", return_value=fake):
        result = DeleteBlockToolHandler().run_tool({"block_uuid": "u6"})
        assert "Successfully deleted" in result[0].text
        fake.get_block_page_name.assert_not_called()


def test_get_block_denies_when_page_tag_excluded():
    """A block in an ALLOWED namespace but whose owning page carries an excluded
    tag (#keys) must be denied. Namespace passes; the tag guard must catch it."""
    fake = Mock()
    fake.get_block_page_name.return_value = "work/vault"  # allowed namespace
    fake.get_page_content.return_value = {"page": {"properties": {"tags": ["keys"]}}}
    with patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=["work"],
        _exclude_namespaces=[],
        _exclude_tags=["keys"],
    ), patch("mcp_logseq.tools._make_api", return_value=fake):
        with pytest.raises(AccessDenied):
            GetBlockToolHandler().run_tool({"block_uuid": "u-tag"})


def test_get_block_allowed_when_page_not_tag_excluded():
    """Control: a block whose owning page has no excluded tag still returns."""
    fake = Mock()
    fake.get_block_page_name.return_value = "work/vault"
    fake.get_page_content.return_value = {"page": {"properties": {"tags": ["notes"]}}}
    fake.get_block.return_value = {"content": "visible block content", "children": []}
    with patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=["work"],
        _exclude_namespaces=[],
        _exclude_tags=["keys"],
    ), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = GetBlockToolHandler().run_tool({"block_uuid": "u-ok"})[0].text
        assert "visible block content" in out


def test_set_block_properties_denies():
    # set_block_properties only runs in DB mode; patch _db_mode so the handler
    # reaches the enforcement call rather than returning the DB-mode guard early.
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True):
        with pytest.raises(AccessDenied):
            SetBlockPropertiesToolHandler().run_tool(
                {"block_uuid": "u7", "properties": {"k": "v"}}
            )


# =============================================================================
# Task 4: Content-returning tool ACL audit
#
# Every registered tool that can return page/block CONTENT must enforce the
# namespace/tag guard. The HTTP transport exposes the full tool set, so a guard
# gap = a data-exfiltration path. Status determined by reading each run_tool:
#
#   Tool                            Guard status
#   ------------------------------  ---------------------------------------------
#   get_page_content                GUARDED  (pre-flight + _is_page_blocked)
#   list_pages                      GUARDED  (_is_page_blocked filter)
#   search                          GUARDED  (_build_excluded_page_names filter)
#   query (DSL)                     FIXED    (was: pages-only; now blocks too)
#   find_pages_by_property          GUARDED  (_is_page_blocked filter)
#   get_page_backlinks              GUARDED  (pre-flight + per-referrer filter)
#   get_pages_from_namespace        GUARDED  (pre-flight + filter)
#   get_pages_tree_from_namespace   GUARDED  (pre-flight + prune)
#   get_block                       GUARDED  (_enforce_block_namespace_access)
#   vector_search                   FIXED    (was: namespace-only; now tags too)
#
# Non-content/write tools (create/update/delete/rename/insert/set_block_props)
# enforce the guard too, but are covered above (Task 1-3 tests) — they cannot
# leak existing content.
# =============================================================================


# =============================================================================
# Task 7: Silent filtering in list/search/query/find_pages_by_property
# =============================================================================

from mcp_logseq.tools import (
    ListPagesToolHandler,
    SearchToolHandler,
    QueryToolHandler,
    FindPagesByPropertyToolHandler,
)


def test_list_pages_hides_blocked_namespace():
    pages = [
        {"originalName": "work/projects", "properties": {}},
        {"originalName": "finance/q3", "properties": {}},
    ]
    fake = Mock()
    fake.list_pages.return_value = pages
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = ListPagesToolHandler().run_tool({})[0].text
        assert "work/projects" in out
        assert "finance/q3" not in out


def test_list_pages_strict_allowlist_hides_unnamespaced():
    pages = [
        {"originalName": "work/projects", "properties": {}},
        {"originalName": "Fikirler", "properties": {}},
    ]
    fake = Mock()
    fake.list_pages.return_value = pages
    with _ns(include=["work"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = ListPagesToolHandler().run_tool({})[0].text
        assert "work/projects" in out
        assert "Fikirler" not in out


def test_search_excludes_blocked_namespace_pages():
    fake = Mock()
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        names = SearchToolHandler._build_excluded_page_names(
            fake, [], ["finance"], []
        )
        assert "finance/q3" in names
        assert "work/x" not in names


def test_markdown_search_suppresses_unidentified_blocks_when_excluding_text():
    """Markdown-mode 'blocks' carry block/content but no page id. When any
    exclusion is active they cannot be verified safe, so the whole blocks
    section must be suppressed in text output (mirrors the snippets guard)."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [{"block/content": "secret api token AKIA-leak"}],
        "pages": ["work/x"],
    }
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=False), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "token"})[0].text
        assert "AKIA-leak" not in out
        assert "Content Blocks" not in out
        assert "work/x" in out  # identified pages still surface


def test_markdown_search_suppresses_unidentified_blocks_when_excluding_json():
    """Same suppression must apply on the JSON output path."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [{"block/content": "secret api token AKIA-leak"}],
        "pages": ["work/x"],
    }
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=False), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "token", "format": "json"})[0].text
        assert "AKIA-leak" not in out
        parsed = json.loads(out)
        assert "blocks" not in parsed  # unidentified blocks omitted
        assert parsed["pages"] == ["work/x"]


def test_markdown_search_shows_blocks_when_no_exclusion():
    """Control: with no exclusion active, the blocks section still appears."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [{"block/content": "ordinary visible block"}],
        "pages": ["work/x"],
    }
    fake.list_pages.return_value = []
    with _ns(), \
            patch("mcp_logseq.tools._get_db_mode", return_value=False), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "block"})[0].text
        assert "ordinary visible block" in out
        assert "Content Blocks" in out


def test_query_hides_blocked_page_objects():
    fake = Mock()
    fake.query_dsl.return_value = [
        {"originalName": "finance/q3"},
        {"originalName": "work/x"},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(page-property x)"})[0].text
        assert "work/x" in out
        assert "finance/q3" not in out


def test_find_pages_by_property_hides_blocked_pages():
    fake = Mock()
    fake.query_dsl.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = FindPagesByPropertyToolHandler().run_tool({"property_name": "status"})[0].text
        assert "work/x" in out
        assert "finance/q3" not in out


def test_get_page_backlinks_filters_blocked_referrers():
    """Backlinks from blocked namespaces must be silently omitted from the result.

    The queried page itself is allowed (work/projects passes the pre-flight).
    The API returns two referencing entries: one from a blocked page
    (finance/q3, in excluded namespace 'finance') and one from an allowed page
    (work/x).  Only work/x should appear in the output.
    """
    fake = Mock()
    # Real shape: [[PageEntity, [BlockEntity, ...]], ...]
    fake.get_page_linked_references.return_value = [
        [
            {"originalName": "finance/q3"},
            [{"content": "See [[work/projects]] for context"}],
        ],
        [
            {"originalName": "work/x"},
            [{"content": "Linked from [[work/projects]]"}],
        ],
    ]

    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = GetPageBacklinksToolHandler().run_tool({"page_name": "work/projects"})[0].text

    assert "work/x" in out
    assert "finance/q3" not in out
    # Footer count must reflect only the 1 shown page, not the 2 raw entries —
    # an overcount would leak the existence of the hidden referrer.
    assert "Total: 1 page," in out
    assert "Total: 2 pages" not in out


def test_vector_results_filtered_by_namespace():
    pytest.importorskip("mcp_logseq.vector.index")
    from mcp_logseq.vector.index import _filter_results_by_namespace

    class R:
        def __init__(self, page):
            self.page = page

    results = [R("work/x"), R("finance/q3"), R("Fikirler")]
    kept = _filter_results_by_namespace(results, include=["work"], exclude=[])
    pages = [r.page for r in kept]
    assert pages == ["work/x"]  # strict allow-list drops finance and unnamespaced


def test_get_pages_from_namespace_filters_excluded_subnamespace():
    fake = Mock()
    fake.get_pages_from_namespace.return_value = [
        {"originalName": "work/projects"},
        {"originalName": "work/secret/keys"},
    ]
    with _ns(include=["work"], exclude=["work/secret"]), patch(
        "mcp_logseq.tools._make_api", return_value=fake
    ):
        out = GetPagesFromNamespaceToolHandler().run_tool({"namespace": "work"})[0].text
        assert "work/projects" in out
        assert "work/secret/keys" not in out


def test_get_pages_tree_from_namespace_prunes_excluded_subnamespace():
    fake = Mock()
    fake.get_pages_tree_from_namespace.return_value = [
        {
            "originalName": "work",
            "children": [
                {"originalName": "work/projects", "children": []},
                {
                    "originalName": "work/secret",
                    "children": [
                        {"originalName": "work/secret/keys", "children": []},
                    ],
                },
            ],
        },
    ]
    with _ns(include=["work"], exclude=["work/secret"]), patch(
        "mcp_logseq.tools._make_api", return_value=fake
    ):
        out = GetPagesTreeFromNamespaceToolHandler().run_tool({"namespace": "work"})[0].text
        assert "work/projects" in out
        assert "work/secret" not in out  # whole subtree pruned (also covers .../keys)


# =============================================================================
# Task 4: DSL query must filter BLOCK results from denied namespaces, not just
# page objects. A block-returning query (e.g. (page-tags)) could otherwise
# surface block content owned by a blocked page.
# =============================================================================


def test_query_filters_blocks_from_blocked_namespace_via_inline_page():
    """A block carrying an inline page ref to a blocked namespace is dropped."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "secret salary data", "page": {"originalName": "finance/q3"}},
        {"content": "public roadmap", "page": {"originalName": "work/x"}},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(page-tags)"})[0].text
        assert "public roadmap" in out
        assert "secret salary data" not in out
        assert "finance/" not in out


def test_query_filters_blocks_via_api_page_resolution():
    """A block lacking an inline page ref is resolved via the API and filtered."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "secret data", "uuid": "blk-1"},
    ]
    fake.get_block_page_name.return_value = "finance/q3"
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(task TODO)"})[0].text
        assert "secret data" not in out
        # Assert the empty branch was taken — not silently swallowed elsewhere.
        assert "No results" in out


def test_query_filters_block_with_bare_uuid_page_ref():
    """A block whose inline 'page' is a bare UUID string must be resolved, not
    trusted. Under an exclude-only policy a raw UUID matches no rule, so trusting
    it would fail OPEN. The UUID must resolve to its real (denied) page name."""
    denied_uuid = "12345678-1234-1234-1234-123456789abc"
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "secret salary data", "page": denied_uuid},
    ]
    fake.resolve_page_uuids.return_value = {denied_uuid: "Private/Secret"}
    with _ns(exclude=["private"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(page-tags)"})[0].text
        assert "secret salary data" not in out
        assert denied_uuid not in out
        assert "No results" in out
        fake.resolve_page_uuids.assert_called_once_with([denied_uuid])


def test_query_block_denied_when_page_unresolvable_and_rules_set():
    """Fail-closed: a block whose owning page cannot be resolved is dropped."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "unverifiable block", "uuid": "blk-x"},
    ]
    fake.get_block_page_name.return_value = None
    with _ns(include=["work"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(task TODO)"})[0].text
        assert "unverifiable block" not in out
        # Tighten: assert the tool reported the empty branch, so a bug that
        # swallows the item into the non-empty render path cannot pass.
        assert "No results" in out


def test_query_block_json_format_also_filtered():
    """JSON output path must apply the same block filtering as text."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "secret", "page": {"originalName": "finance/q3"}},
        {"content": "ok", "page": {"originalName": "work/x"}},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool(
            {"query": "(page-tags)", "format": "json"}
        )[0].text
        assert "ok" in out
        assert "secret" not in out


def test_query_blocks_pass_when_no_rules():
    """No ACL rules => blocks pass through untouched, no API resolution calls."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "anything", "uuid": "blk-1"},
    ]
    with _ns(), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(task TODO)"})[0].text
        assert "anything" in out
        fake.get_block_page_name.assert_not_called()


# =============================================================================
# LEAK 1: DB-mode search must filter block results whose owning page is excluded
# (both namespace and tag axes), in BOTH text and JSON output paths.
# DB-mode blocks carry a 'page' field = owning page UUID, so they are resolvable.
# =============================================================================


def test_db_search_filters_block_from_excluded_namespace_text():
    """DB-mode text output must drop a block whose owning page is namespace-excluded."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "secret salary AKIA-leak", "uuid": "blk-1", "page": "uuid-fin"},
            {"content": "public roadmap data", "uuid": "blk-2", "page": "uuid-work"},
        ],
    }
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    fake.resolve_page_uuids.return_value = {
        "uuid-fin": "finance/q3",
        "uuid-work": "work/x",
    }
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "data"})[0].text
        assert "AKIA-leak" not in out
        assert "blk-1" not in out
        assert "public roadmap data" in out


def test_db_search_filters_block_from_excluded_namespace_json():
    """DB-mode JSON output must drop a block whose owning page is namespace-excluded."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "secret salary AKIA-leak", "uuid": "blk-1", "page": "uuid-fin"},
            {"content": "public roadmap data", "uuid": "blk-2", "page": "uuid-work"},
        ],
    }
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    fake.resolve_page_uuids.return_value = {
        "uuid-fin": "finance/q3",
        "uuid-work": "work/x",
    }
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool(
            {"query": "data", "format": "json"}
        )[0].text
        assert "AKIA-leak" not in out
        assert "blk-1" not in out
        parsed = json.loads(out)
        uuids = [b.get("uuid") for b in parsed.get("blocks", [])]
        assert "blk-1" not in uuids
        assert "blk-2" in uuids


def test_db_search_filters_block_from_tag_excluded_page_text():
    """DB-mode text output must drop a block whose owning page is TAG-excluded."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "secret key AKIA-leak", "uuid": "blk-1", "page": "uuid-vault"},
            {"content": "ordinary note", "uuid": "blk-2", "page": "uuid-notes"},
        ],
    }
    fake.list_pages.return_value = [
        {"originalName": "vault", "properties": {"tags": ["keys"]}},
        {"originalName": "notes", "properties": {}},
    ]
    fake.resolve_page_uuids.return_value = {
        "uuid-vault": "vault",
        "uuid-notes": "notes",
    }
    with patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=[],
        _exclude_namespaces=[],
        _exclude_tags=["keys"],
    ), patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "note"})[0].text
        assert "AKIA-leak" not in out
        assert "blk-1" not in out
        assert "ordinary note" in out


def test_db_search_block_fail_closed_when_unresolvable():
    """Fail-closed: a DB-mode block whose owning page cannot be resolved is dropped
    while an exclusion rule is active."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "unverifiable AKIA-leak", "uuid": "blk-1", "page": "uuid-???"},
        ],
    }
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
    ]
    fake.resolve_page_uuids.return_value = {}  # cannot resolve
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "x"})[0].text
        assert "AKIA-leak" not in out


def test_db_search_blocks_pass_when_no_rules():
    """Control: with no exclusion active, DB-mode blocks surface and no UUID
    resolution call is made."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "ordinary visible block", "uuid": "blk-1", "page": "uuid-1"},
        ],
    }
    fake.list_pages.return_value = []
    with _ns(), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "block"})[0].text
        assert "ordinary visible block" in out
        fake.resolve_page_uuids.assert_not_called()


def test_db_search_fails_closed_when_list_pages_raises_with_rules():
    """Fail-closed: if list_pages() throws while a rule is active, the search
    must NOT surface DB-mode block content (it returns an error instead of an
    unfiltered, degraded result set)."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "secret AKIA-leak", "uuid": "blk-1", "page": "uuid-fin"},
        ],
    }
    fake.list_pages.side_effect = RuntimeError("api down")
    with _ns(exclude=["finance"]), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "x"})[0].text
        assert "AKIA-leak" not in out
        assert "Search failed" in out


def test_search_no_rules_unaffected_by_list_pages():
    """Control: with NO rules, _build_excluded_page_names returns early and never
    calls list_pages, so a list_pages fault cannot break search."""
    fake = Mock()
    fake.search_content.return_value = {
        "blocks": [
            {"content": "ordinary visible block", "uuid": "blk-1", "page": "uuid-1"},
        ],
    }
    fake.list_pages.side_effect = RuntimeError("api down")
    with _ns(), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True), \
            patch("mcp_logseq.tools._make_api", return_value=fake):
        out = SearchToolHandler().run_tool({"query": "block"})[0].text
        assert "ordinary visible block" in out
        fake.list_pages.assert_not_called()


# =============================================================================
# LEAK 2: tag-only DSL query profile must filter block results whose owning
# page is TAG-excluded (no namespace rules set).
# =============================================================================


def test_query_filters_block_from_tag_excluded_page():
    """With ONLY exclude_tags set (no namespace rules), a query block whose owning
    page carries an excluded tag must be dropped."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "secret key AKIA-leak", "page": {"originalName": "vault"}},
        {"content": "public note", "page": {"originalName": "notes"}},
    ]

    def _content(page_name):
        if page_name == "vault":
            return {"page": {"properties": {"tags": ["keys"]}}}
        return {"page": {"properties": {}}}

    fake.get_page_content.side_effect = _content
    with patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=[],
        _exclude_namespaces=[],
        _exclude_tags=["keys"],
    ), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(page-tags)"})[0].text
        assert "AKIA-leak" not in out
        assert "public note" in out


def test_query_blocks_pass_when_no_rules_tag_axis():
    """Control: with no rules at all, blocks pass through (no tag fetch)."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "anything", "page": {"originalName": "vault"}},
    ]
    with _ns(), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(task TODO)"})[0].text
        assert "anything" in out
        fake.get_page_content.assert_not_called()


def test_query_tag_fetch_deduped_per_owning_page():
    """Two blocks from the SAME owning page must trigger get_page_content only
    once within a single query run (per-request memo)."""
    fake = Mock()
    fake.query_dsl.return_value = [
        {"content": "alpha", "page": {"originalName": "notes"}},
        {"content": "beta", "page": {"originalName": "notes"}},
    ]
    fake.get_page_content.return_value = {"page": {"properties": {}}}
    with patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=[],
        _exclude_namespaces=[],
        _exclude_tags=["keys"],
    ), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(task TODO)"})[0].text
        assert "alpha" in out
        assert "beta" in out
        assert fake.get_page_content.call_count == 1


# =============================================================================
# Task 4b: vector_search must apply _exclude_tags, not just namespace rules.
# On a shared DB, a #keys-tagged chunk physically present in the index must not
# surface for a profile that excludes the 'keys' tag.
# =============================================================================


def test_vector_results_filtered_by_tags():
    pytest.importorskip("mcp_logseq.vector.index")
    from mcp_logseq.vector.index import _filter_results_by_tags

    class R:
        def __init__(self, tags):
            self.tags = tags

    results = [R(["notes"]), R(["keys"]), R(["keys", "notes"]), R([])]
    kept = _filter_results_by_tags(results, exclude_tags=["keys"])
    assert [r.tags for r in kept] == [["notes"], []]


# =============================================================================
# Task 5 Step 1: Regression guard for existing PR #65 write gating.
# These pin current behavior so the --read-only refactor cannot regress it.
# Every genuine write tool targeting an excluded namespace must raise.
# =============================================================================


def _priv():
    """Patch config so the 'Private' namespace is excluded."""
    return patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=[],
        _exclude_namespaces=["Private"],
        _exclude_tags=[],
    )


def test_regression_create_page_denies_private():
    with _priv():
        with pytest.raises(AccessDenied):
            CreatePageToolHandler().run_tool({"title": "Private/x", "content": "c"})


def test_regression_update_page_denies_private():
    with _priv():
        with pytest.raises(AccessDenied):
            UpdatePageToolHandler().run_tool({"page_name": "Private/x", "content": "c"})


def test_regression_delete_page_denies_private():
    with _priv():
        with pytest.raises(AccessDenied):
            DeletePageToolHandler().run_tool({"page_name": "Private/x"})


def test_regression_update_block_denies_private():
    with _priv(), _api_with_block_page("Private/x"):
        with pytest.raises(AccessDenied):
            UpdateBlockToolHandler().run_tool({"block_uuid": "u1", "content": "c"})


def test_regression_delete_block_denies_private():
    with _priv(), _api_with_block_page("Private/x"):
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u1"})


def test_regression_insert_nested_block_denies_private():
    with _priv(), _api_with_block_page("Private/x"):
        with pytest.raises(AccessDenied):
            InsertNestedBlockToolHandler().run_tool(
                {"parent_block_uuid": "u1", "content": "c"}
            )


def test_regression_set_block_properties_denies_private():
    with _priv(), _api_with_block_page("Private/x"), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True):
        with pytest.raises(AccessDenied):
            SetBlockPropertiesToolHandler().run_tool(
                {"block_uuid": "u1", "properties": {"k": "v"}}
            )


def test_regression_rename_page_denies_when_old_private():
    with _priv():
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool(
                {"old_name": "Private/x", "new_name": "Public/x"}
            )


def test_regression_rename_page_denies_when_new_private():
    with _priv():
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool(
                {"old_name": "Public/x", "new_name": "Private/x"}
            )


# =============================================================================
# Task 5 Step 2a: --read-only unregisters genuine write tools only.
# =============================================================================

# Single source of truth — import the server's set rather than duplicating it,
# so the test and the implementation can't drift.
from mcp_logseq.server import _WRITE_TOOL_NAMES as _GENUINE_WRITE_TOOLS


def test_read_only_unregisters_all_write_tools():
    from mcp_logseq.server import build_app

    _, handlers = build_app(read_only=True)
    for name in _GENUINE_WRITE_TOOLS:
        assert name not in handlers, f"{name} must be absent under read_only"


def test_read_only_keeps_read_tools():
    from mcp_logseq.server import build_app

    _, handlers = build_app(read_only=True)
    for name in [
        "list_pages",
        "get_page_content",
        "get_block",
        "search",
        "query",
        "find_pages_by_property",
        "get_pages_from_namespace",
        "get_pages_tree_from_namespace",
        "get_page_backlinks",
    ]:
        assert name in handlers, f"read tool {name} must remain under read_only"


def test_default_build_app_registers_write_tools():
    from mcp_logseq.server import build_app

    _, handlers = build_app()
    for name in _GENUINE_WRITE_TOOLS:
        assert name in handlers, f"{name} must be present by default"


def test_read_only_keeps_sync_and_vector_tools(monkeypatch, tmp_path):
    """sync_vector_db is NOT a genuine write tool; vector tools stay registered."""
    pytest.importorskip("mcp_logseq.vector.index")

    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "logseq_graph_path": str(tmp_path),
        "vector": {
            "enabled": True,
            "db_path": str(tmp_path / "db"),
            "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
        },
    }))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))

    from mcp_logseq.server import build_app

    _, handlers = build_app(read_only=True)
    for name in ["vector_search", "vector_db_status", "sync_vector_db"]:
        assert name in handlers, f"{name} must remain under read_only"


# =============================================================================
# Task 5 Step 2b: tag-on-write — writes to a tag-excluded EXISTING page in an
# ALLOWED namespace must be denied. create_page is exempt (no prior tags).
# =============================================================================


def _tagged_page_api(tag="keys"):
    """Mock _make_api so get_page_content returns a page carrying ``tag``."""
    fake = Mock()
    fake.get_page_content.return_value = {
        "page": {"originalName": "work/secrets", "properties": {"tags": [tag]}},
        "blocks": [],
    }
    fake.get_block_page_name.return_value = "work/secrets"
    return patch("mcp_logseq.tools._make_api", return_value=fake)


def _tags_excluded(tag="keys"):
    return patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=[],
        _exclude_namespaces=[],
        _exclude_tags=[tag],
    )


def test_update_page_denies_tag_excluded_existing_page():
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            UpdatePageToolHandler().run_tool(
                {"page_name": "work/secrets", "content": "c"}
            )


def test_delete_page_denies_tag_excluded_existing_page():
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            DeletePageToolHandler().run_tool({"page_name": "work/secrets"})


def test_update_block_denies_tag_excluded_owning_page():
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            UpdateBlockToolHandler().run_tool({"block_uuid": "u1", "content": "c"})


def test_delete_block_denies_tag_excluded_owning_page():
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u1"})


def test_set_block_properties_denies_tag_excluded_owning_page():
    with _tags_excluded(), _tagged_page_api(), \
            patch("mcp_logseq.tools._get_db_mode", return_value=True):
        with pytest.raises(AccessDenied):
            SetBlockPropertiesToolHandler().run_tool(
                {"block_uuid": "u1", "properties": {"k": "v"}}
            )


def test_create_page_exempt_from_tag_on_write():
    """create_page must NOT fetch/inspect prior tags — a new page has none."""
    fake = Mock()
    fake.page_exists.return_value = False
    fake.create_page_with_blocks.return_value = {"name": "work/fresh"}
    with _tags_excluded(), patch("mcp_logseq.tools._make_api", return_value=fake):
        # Should not raise on tag grounds (namespace allows it).
        CreatePageToolHandler().run_tool({"title": "work/fresh", "content": "c"})
        fake.get_page_content.assert_not_called()


def test_insert_nested_block_denies_tag_excluded_owning_page():
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            InsertNestedBlockToolHandler().run_tool(
                {"parent_block_uuid": "u1", "content": "c"}
            )


def test_rename_page_denies_tag_excluded_source_page():
    """Renaming a tag-excluded existing SOURCE page is denied (target is new)."""
    with _tags_excluded(), _tagged_page_api():
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool(
                {"old_name": "work/secrets", "new_name": "work/renamed"}
            )
        # rename_page must guard only the source — never fetch the (new) target.


def test_tag_on_write_fails_closed_when_page_fetch_raises():
    """With exclude tags configured, a page-fetch error must abort the write
    rather than silently proceeding (no fail-open). The error propagates and the
    write API is never called."""
    fake = Mock()
    fake.get_page_content.side_effect = RuntimeError("API down")
    with _tags_excluded(), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = UpdatePageToolHandler().run_tool(
            {"page_name": "work/secrets", "content": "c"}
        )
        # The write did NOT succeed: update_page_with_blocks never ran, and the
        # handler reported failure rather than success.
        fake.update_page_with_blocks.assert_not_called()
        assert "Successfully updated" not in out[0].text


def test_vector_search_drops_tag_excluded_chunk(monkeypatch):
    """A #keys chunk in the shared DB must not surface when 'keys' is excluded."""
    pytest.importorskip("mcp_logseq.vector.index")
    import mcp_logseq.vector.index as vindex
    from mcp_logseq.vector.index import VectorSearchToolHandler
    from mcp_logseq.vector.types import SearchResult

    config = Mock()
    config.db_path = "/tmp/test-vector-db"
    config.graph_path = "/tmp/test-graph"
    config.embedder = "ollama/x"

    secret = SearchResult(
        page="ApiKeys", text="AKIA-secret-token", raw="", score=0.1,
        tags=["keys"], date=None, properties={}, chunk_index=0,
    )
    ok = SearchResult(
        page="Roadmap", text="public roadmap", raw="", score=0.2,
        tags=["notes"], date=None, properties={}, chunk_index=0,
    )

    meta = Mock()
    meta.embedder_key = "ollama/x"
    meta.dimensions = 3

    with (
        patch.object(vindex, "_exclude_tags", ["keys"]),
        patch.object(vindex, "_include_namespaces", []),
        patch.object(vindex, "_exclude_namespaces", []),
        patch("mcp_logseq.vector.index.StateManager") as mock_sm,
        patch("mcp_logseq.vector.index.check_staleness") as mock_stale,
        patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
        patch("mcp_logseq.vector.index.VectorDB") as mock_db,
    ):
        mock_sm.return_value.load.return_value = ({}, meta)
        mock_stale.return_value = Mock(stale=False)
        mock_emb.return_value.key = meta.embedder_key
        mock_emb.return_value.embed.return_value = [[0.1, 0.1, 0.1]]
        mock_db.open_readonly.return_value.search.return_value = [secret, ok]

        out = VectorSearchToolHandler(config).run_tool({"query": "keys"})[0].text
        assert "public roadmap" in out
        assert "AKIA-secret-token" not in out
        assert "ApiKeys" not in out
