import json
import os
import tempfile

import pytest

from mcp_logseq.config import load_vector_config


def _write_config(tmp_path, data: dict) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_returns_none_when_env_not_set(monkeypatch):
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_vector_config() is None


def test_returns_none_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(tmp_path / "nonexistent.json"))
    assert load_vector_config() is None


def test_returns_none_when_vector_disabled(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {"enabled": False},
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    assert load_vector_config() is None


def test_returns_none_when_vector_missing(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {"logseq_graph_path": "/some/path"})
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    assert load_vector_config() is None


def test_returns_none_when_graph_path_missing(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "vector": {
            "enabled": True,
            "db_path": "/tmp/db",
            "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
        }
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    assert load_vector_config() is None


def test_returns_none_for_unsupported_provider(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "db_path": "/tmp/db",
            "embedder": {"provider": "openai", "model": "text-embedding-3-small"},
        }
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    assert load_vector_config() is None


def test_loads_valid_config(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/my/graph/pages",
        "vector": {
            "enabled": True,
            "db_path": "~/.logseq-vector",
            "embedder": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "base_url": "http://localhost:11434",
            },
            "include_journals": False,
            "exclude_tags": ["private", "draft"],
            "min_chunk_length": 100,
            "watch_debounce_ms": 3000,
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    config = load_vector_config()
    assert config is not None
    assert config.enabled is True
    assert config.graph_path == "/my/graph/pages"
    assert config.include_journals is False
    assert config.exclude_tags == ["private", "draft"]
    assert config.min_chunk_length == 100
    assert config.watch_debounce_ms == 3000
    assert config.embedder.provider == "ollama"
    assert config.embedder.model == "nomic-embed-text"


def test_applies_defaults(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/my/graph/pages",
        "vector": {
            "enabled": True,
            "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    config = load_vector_config()
    assert config is not None
    assert config.include_journals is True
    assert config.exclude_tags == []
    assert config.min_chunk_length == 50
    assert config.watch_debounce_ms == 5000
    assert config.embedder.base_url == "http://localhost:11434"
