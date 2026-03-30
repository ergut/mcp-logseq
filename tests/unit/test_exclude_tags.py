"""Tests for the exclude_tags security feature.

Covers:
- load_exclude_tags() config loading (env var, config file, priority)
- _extract_tags() and _is_page_excluded() helper functions
- ListPagesToolHandler filtering
- GetPageContentToolHandler access denial
- SearchToolHandler page filtering
- QueryToolHandler page object filtering
"""

import json
import pytest
from unittest.mock import patch, Mock

from mcp_logseq.config import load_exclude_tags
from mcp_logseq.tools import (
    _extract_tags,
    _is_page_excluded,
    ListPagesToolHandler,
    GetPageContentToolHandler,
    SearchToolHandler,
    QueryToolHandler,
)


# =============================================================================
# load_exclude_tags()
# =============================================================================


def test_returns_empty_when_nothing_set(monkeypatch):
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_tags() == []


def test_reads_from_env_var(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", "private,secret")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_tags() == ["private", "secret"]


def test_env_var_strips_whitespace(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", " private , secret ")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_tags() == ["private", "secret"]


def test_env_var_takes_priority_over_config_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_tags": ["from-file"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", "from-env")
    assert load_exclude_tags() == ["from-env"]


def test_reads_from_config_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_tags": ["private", "draft"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    assert load_exclude_tags() == ["private", "draft"]


def test_config_file_comma_string_form(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_tags": "private, draft"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    assert load_exclude_tags() == ["private", "draft"]


def test_returns_empty_when_config_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(tmp_path / "nonexistent.json"))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    assert load_exclude_tags() == []


def test_returns_empty_when_config_file_malformed(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("not valid json{{{")
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    assert load_exclude_tags() == []


def test_returns_empty_when_config_has_no_exclude_tags_key(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"logseq_graph_path": "/some/path"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_TAGS", raising=False)
    assert load_exclude_tags() == []


def test_env_var_empty_string_falls_through_to_config(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_tags": ["from-file"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", "")
    assert load_exclude_tags() == ["from-file"]


# =============================================================================
# _extract_tags() and _is_page_excluded()
# =============================================================================


def test_extract_tags_list_form():
    assert _extract_tags({"tags": ["private", "draft"]}) == ["private", "draft"]


def test_extract_tags_string_form():
    assert _extract_tags({"tags": "private, draft"}) == ["private", "draft"]


def test_extract_tags_missing_key():
    assert _extract_tags({}) == []


def test_extract_tags_empty_list():
    assert _extract_tags({"tags": []}) == []


def test_extract_tags_strips_whitespace():
    assert _extract_tags({"tags": " private , draft "}) == ["private", "draft"]


def test_is_page_excluded_true():
    page = {"properties": {"tags": ["private", "notes"]}}
    assert _is_page_excluded(page, ["private"]) is True


def test_is_page_excluded_false():
    page = {"properties": {"tags": ["public", "notes"]}}
    assert _is_page_excluded(page, ["private"]) is False


def test_is_page_excluded_empty_exclude_list():
    page = {"properties": {"tags": ["private"]}}
    assert _is_page_excluded(page, []) is False


def test_is_page_excluded_no_properties_key():
    page = {"name": "Some Page"}
    assert _is_page_excluded(page, ["private"]) is False


def test_is_page_excluded_none_properties():
    page = {"properties": None}
    assert _is_page_excluded(page, ["private"]) is False


# =============================================================================
# ListPagesToolHandler
# =============================================================================


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_list_pages_excludes_tagged_pages(mock_logseq_class):
    mock_api = Mock()
    mock_api.list_pages.return_value = [
        {"originalName": "Public Page", "journal?": False, "properties": {"tags": ["notes"]}},
        {"originalName": "Secret Page", "journal?": False, "properties": {"tags": ["private"]}},
        {"originalName": "Normal Page", "journal?": False, "properties": {}},
    ]
    mock_logseq_class.return_value = mock_api

    handler = ListPagesToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"include_journals": True})

    text = result[0].text
    assert "Public Page" in text
    assert "Normal Page" in text
    assert "Secret Page" not in text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_list_pages_no_filter_when_exclude_empty(mock_logseq_class):
    mock_api = Mock()
    mock_api.list_pages.return_value = [
        {"originalName": "Private Page", "journal?": False, "properties": {"tags": ["private"]}},
    ]
    mock_logseq_class.return_value = mock_api

    handler = ListPagesToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", []):
        result = handler.run_tool({})

    assert "Private Page" in result[0].text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_list_pages_multiple_excluded_tags(mock_logseq_class):
    mock_api = Mock()
    mock_api.list_pages.return_value = [
        {"originalName": "Secret", "journal?": False, "properties": {"tags": ["private"]}},
        {"originalName": "Draft", "journal?": False, "properties": {"tags": ["draft"]}},
        {"originalName": "Public", "journal?": False, "properties": {"tags": ["notes"]}},
    ]
    mock_logseq_class.return_value = mock_api

    handler = ListPagesToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private", "draft"]):
        result = handler.run_tool({})

    text = result[0].text
    assert "Public" in text
    assert "Secret" not in text
    assert "Draft" not in text


# =============================================================================
# GetPageContentToolHandler
# =============================================================================


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_get_page_content_raises_for_excluded_page(mock_logseq_class):
    mock_api = Mock()
    mock_api.get_page_content.return_value = {
        "page": {"originalName": "Secret Diary", "properties": {"tags": ["private"]}},
        "blocks": [{"content": "top secret stuff", "children": []}],
    }
    mock_logseq_class.return_value = mock_api

    handler = GetPageContentToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        with pytest.raises(RuntimeError, match="Access denied"):
            handler.run_tool({"page_name": "Secret Diary"})


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_get_page_content_allows_non_excluded_page(mock_logseq_class):
    mock_api = Mock()
    mock_api.get_page_content.return_value = {
        "page": {"originalName": "Public Notes", "properties": {"tags": ["notes"]}},
        "blocks": [{"content": "Some notes content", "children": []}],
    }
    mock_logseq_class.return_value = mock_api

    handler = GetPageContentToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"page_name": "Public Notes"})

    assert "Some notes content" in result[0].text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_get_page_content_no_block_when_exclude_empty(mock_logseq_class):
    mock_api = Mock()
    mock_api.get_page_content.return_value = {
        "page": {"originalName": "Private Page", "properties": {"tags": ["private"]}},
        "blocks": [{"content": "private content", "children": []}],
    }
    mock_logseq_class.return_value = mock_api

    handler = GetPageContentToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", []):
        result = handler.run_tool({"page_name": "Private Page"})

    assert "private content" in result[0].text


# =============================================================================
# SearchToolHandler
# =============================================================================


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_search_filters_excluded_page_names(mock_logseq_class):
    mock_api = Mock()
    mock_api.list_pages.return_value = [
        {"originalName": "Secret Page", "journal?": False, "properties": {"tags": ["private"]}},
        {"originalName": "Public Page", "journal?": False, "properties": {}},
    ]
    mock_api.search_content.return_value = {
        "blocks": [],
        "pages": ["Secret Page", "Public Page"],
        "pages-content": [],
        "files": [],
    }
    mock_logseq_class.return_value = mock_api

    handler = SearchToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"query": "test"})

    text = result[0].text
    assert "Public Page" in text
    assert "Secret Page" not in text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_search_no_extra_api_call_when_no_exclude_tags(mock_logseq_class):
    """list_pages should NOT be called when _exclude_tags is empty."""
    mock_api = Mock()
    mock_api.search_content.return_value = {
        "blocks": [],
        "pages": ["Some Page"],
        "pages-content": [],
        "files": [],
    }
    mock_logseq_class.return_value = mock_api

    handler = SearchToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", []):
        handler.run_tool({"query": "test"})

    mock_api.list_pages.assert_not_called()


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_search_snippets_dropped_when_exclusion_active(mock_logseq_class):
    """pages-content snippets are dropped when excluded_page_names is non-empty."""
    mock_api = Mock()
    mock_api.list_pages.return_value = [
        {"originalName": "Private", "journal?": False, "properties": {"tags": ["private"]}},
    ]
    mock_api.search_content.return_value = {
        "blocks": [],
        "pages": [],
        "pages-content": [{"block/snippet": "some secret snippet"}],
        "files": [],
    }
    mock_logseq_class.return_value = mock_api

    handler = SearchToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"query": "test"})

    assert "some secret snippet" not in result[0].text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_search_snippets_shown_when_no_exclusion(mock_logseq_class):
    """pages-content snippets are shown when _exclude_tags is empty."""
    mock_api = Mock()
    mock_api.search_content.return_value = {
        "blocks": [],
        "pages": [],
        "pages-content": [{"block/snippet": "a visible snippet"}],
        "files": [],
    }
    mock_logseq_class.return_value = mock_api

    handler = SearchToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", []):
        result = handler.run_tool({"query": "test"})

    assert "a visible snippet" in result[0].text


# =============================================================================
# QueryToolHandler
# =============================================================================


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_query_filters_excluded_page_objects(mock_logseq_class):
    mock_api = Mock()
    mock_api.query_dsl.return_value = [
        {"originalName": "Public Page", "name": "public-page", "properties": {"tags": ["notes"]}},
        {"originalName": "Private Page", "name": "private-page", "properties": {"tags": ["private"]}},
    ]
    mock_logseq_class.return_value = mock_api

    handler = QueryToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"query": "(page-property type x)"})

    text = result[0].text
    assert "Public Page" in text
    assert "Private Page" not in text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_query_block_objects_pass_through(mock_logseq_class):
    """Block objects (no page properties) are not filtered."""
    mock_api = Mock()
    mock_api.query_dsl.return_value = [
        {"content": "A block result with no page props", "uuid": "some-uuid"},
    ]
    mock_logseq_class.return_value = mock_api

    handler = QueryToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", ["private"]):
        result = handler.run_tool({"query": "(page-property type x)"})

    assert "A block result" in result[0].text


@patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
@patch("mcp_logseq.tools.logseq.LogSeq")
def test_query_no_filter_when_exclude_empty(mock_logseq_class):
    mock_api = Mock()
    mock_api.query_dsl.return_value = [
        {"originalName": "Private Page", "name": "private-page", "properties": {"tags": ["private"]}},
    ]
    mock_logseq_class.return_value = mock_api

    handler = QueryToolHandler()
    with patch("mcp_logseq.tools._exclude_tags", []):
        result = handler.run_tool({"query": "(page-property type x)"})

    assert "Private Page" in result[0].text
