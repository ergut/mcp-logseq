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

from mcp_logseq.tools import (
    _namespace_matches,
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


def test_set_block_properties_denies():
    # set_block_properties only runs in DB mode; patch _db_mode so the handler
    # reaches the enforcement call rather than returning the DB-mode guard early.
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"), \
            patch("mcp_logseq.tools._db_mode", True):
        with pytest.raises(AccessDenied):
            SetBlockPropertiesToolHandler().run_tool(
                {"block_uuid": "u7", "properties": {"k": "v"}}
            )


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
