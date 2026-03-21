from unittest.mock import MagicMock, patch

import pytest

from mcp_logseq.config import EmbedderConfig
from mcp_logseq.vector.embedder import OllamaEmbedder, create_embedder


def _mock_response(vectors: list[list[float]]):
    mock = MagicMock()
    mock.json.return_value = {"embeddings": vectors}
    mock.raise_for_status = MagicMock()
    return mock


@patch("mcp_logseq.vector.embedder.requests.post")
def test_embed_returns_vectors(mock_post):
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_post.return_value = _mock_response(vectors)

    embedder = OllamaEmbedder(model="nomic-embed-text")
    result = embedder.embed(["hello", "world"])

    assert result == vectors
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "nomic-embed-text" in str(call_kwargs)


@patch("mcp_logseq.vector.embedder.requests.post")
def test_embed_detects_dimensions(mock_post):
    mock_post.return_value = _mock_response([[0.1] * 768])

    embedder = OllamaEmbedder(model="nomic-embed-text")
    embedder.embed(["test"])

    assert embedder.dimensions == 768


@patch("mcp_logseq.vector.embedder.requests.post")
def test_dimensions_probes_on_first_access(mock_post):
    mock_post.return_value = _mock_response([[0.1] * 512])

    embedder = OllamaEmbedder(model="nomic-embed-text")
    dims = embedder.dimensions  # triggers probe

    assert dims == 512
    mock_post.assert_called_once()


@patch("mcp_logseq.vector.embedder.requests.post")
def test_embed_empty_list_returns_empty(mock_post):
    embedder = OllamaEmbedder(model="nomic-embed-text")
    result = embedder.embed([])
    assert result == []
    mock_post.assert_not_called()


@patch("mcp_logseq.vector.embedder.requests.post")
def test_embed_connection_error_raises_runtime_error(mock_post):
    import requests as req
    mock_post.side_effect = req.ConnectionError()

    embedder = OllamaEmbedder(model="nomic-embed-text", base_url="http://localhost:11434")
    with pytest.raises(RuntimeError, match="Cannot connect to Ollama"):
        embedder.embed(["test"])


@patch("mcp_logseq.vector.embedder.requests.post")
def test_embed_http_error_raises_runtime_error(mock_post):
    import requests as req
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")
    mock_post.return_value = mock_resp

    embedder = OllamaEmbedder(model="nomic-embed-text")
    with pytest.raises(RuntimeError, match="Ollama embedding request failed"):
        embedder.embed(["test"])


def test_key_format():
    embedder = OllamaEmbedder(model="nomic-embed-text")
    assert embedder.key == "ollama/nomic-embed-text"

    embedder2 = OllamaEmbedder(model="mxbai-embed-large")
    assert embedder2.key == "ollama/mxbai-embed-large"


def test_create_embedder_ollama():
    config = EmbedderConfig(provider="ollama", model="nomic-embed-text")
    embedder = create_embedder(config)
    assert isinstance(embedder, OllamaEmbedder)
    assert embedder.key == "ollama/nomic-embed-text"


def test_create_embedder_unknown_provider():
    config = EmbedderConfig(provider="openai", model="text-embedding-3-small")
    with pytest.raises(ValueError, match="Unsupported embedder provider"):
        create_embedder(config)
