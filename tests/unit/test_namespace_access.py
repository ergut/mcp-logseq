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
