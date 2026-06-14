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
