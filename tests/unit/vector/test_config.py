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


def test_returns_none_when_embedder_is_not_an_object(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {"enabled": True, "embedder": "ollama"},
    })
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
            "embedder": {"provider": "cohere", "model": "embed-v4.0"},
        }
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    assert load_vector_config() is None


def test_loads_openai_config_with_provider_defaults(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {
                "provider": "openai",
                "api_key": "test-api-key",
            },
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)

    config = load_vector_config()

    assert config is not None
    assert config.embedder.provider == "openai"
    assert config.embedder.model == "text-embedding-3-small"
    assert config.embedder.base_url == "https://api.openai.com/v1"
    assert config.embedder.api_key == "test-api-key"
    assert config.embedder.dimensions is None


def test_returns_none_when_openai_api_key_missing(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {"provider": "openai"},
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)

    assert load_vector_config() is None


def test_loads_openai_compatible_config(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {
                "provider": "openai-compatible",
                "model": "custom-embed-model",
                "base_url": "https://embeddings.example.com/v1",
                "api_key": "compatible-key",
                "dimensions": 1024,
            },
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)

    config = load_vector_config()

    assert config is not None
    assert config.embedder.provider == "openai-compatible"
    assert config.embedder.model == "custom-embed-model"
    assert config.embedder.base_url == "https://embeddings.example.com/v1"
    assert config.embedder.api_key == "compatible-key"
    assert config.embedder.dimensions == 1024


@pytest.mark.parametrize("missing_field", ["model", "base_url"])
def test_returns_none_when_openai_compatible_field_missing(
    monkeypatch, tmp_path, missing_field
):
    embedder = {
        "provider": "openai-compatible",
        "model": "custom-embed-model",
        "base_url": "https://embeddings.example.com/v1",
    }
    del embedder[missing_field]
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {"enabled": True, "embedder": embedder},
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)

    assert load_vector_config() is None


@pytest.mark.parametrize("dimensions", [0, -1, 1.5, True, "1024"])
def test_returns_none_for_invalid_dimensions(monkeypatch, tmp_path, dimensions):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {
                "provider": "openai",
                "api_key": "test-api-key",
                "dimensions": dimensions,
            },
        },
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


def test_loads_index_time_namespaces(monkeypatch, tmp_path):
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/my/graph/pages",
        "vector": {
            "enabled": True,
            "embedder": {"provider": "ollama", "model": "nomic-embed-text"},
            "include_namespaces": ["Work", "Projects"],
            "exclude_namespaces": ["Work/Secret"],
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    config = load_vector_config()
    assert config is not None
    assert config.include_namespaces == ["Work", "Projects"]
    assert config.exclude_namespaces == ["Work/Secret"]


def test_index_time_namespaces_default_empty(monkeypatch, tmp_path):
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
    assert config.include_namespaces == []
    assert config.exclude_namespaces == []


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
