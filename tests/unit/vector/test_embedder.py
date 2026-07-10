from unittest.mock import MagicMock, patch

import pytest

from mcp_logseq.config import EmbedderConfig
from mcp_logseq.vector.embedder import (
    OllamaEmbedder,
    OpenAICompatibleEmbedder,
    create_embedder,
)


def _mock_response(vectors: list[list[float]]):
    mock = MagicMock()
    mock.json.return_value = {"embeddings": vectors}
    mock.raise_for_status = MagicMock()
    return mock


def _mock_openai_response(vectors: list[list[float]], indices: list[int] | None = None):
    mock = MagicMock()
    if indices is None:
        indices = list(range(len(vectors)))
    mock.json.return_value = {
        "data": [
            {"object": "embedding", "embedding": vector, "index": index}
            for vector, index in zip(vectors, indices)
        ]
    }
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
    config = EmbedderConfig(provider="cohere", model="embed-v4.0")
    with pytest.raises(ValueError, match="Unsupported embedder provider"):
        create_embedder(config)


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_embed_sends_auth_payload_and_restores_index_order(mock_post):
    vectors = [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]
    mock_post.return_value = _mock_openai_response(vectors, indices=[1, 0])
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1/",
        api_key="test-api-key",
    )

    result = embedder.embed(["first", "second"])

    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_post.assert_called_once_with(
        "https://api.openai.com/v1/embeddings",
        json={
            "model": "text-embedding-3-small",
            "input": ["first", "second"],
            "encoding_format": "float",
        },
        headers={"Authorization": "Bearer test-api-key"},
        timeout=120,
    )


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_compatible_omits_auth_and_sends_dimensions(mock_post):
    mock_post.return_value = _mock_openai_response([[0.1] * 256])
    embedder = OpenAICompatibleEmbedder(
        provider="openai-compatible",
        model="custom-model",
        base_url="http://localhost:8080/v1",
        dimensions=256,
    )

    assert embedder.dimensions == 256
    result = embedder.embed(["test"])

    assert len(result[0]) == 256
    call = mock_post.call_args
    assert call.kwargs["headers"] == {}
    assert call.kwargs["json"]["dimensions"] == 256


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_dimensions_probes_when_not_configured(mock_post):
    mock_post.return_value = _mock_openai_response([[0.1] * 1536])
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
    )

    assert embedder.dimensions == 1536
    mock_post.assert_called_once()


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_embed_empty_list_returns_empty(mock_post):
    embedder = OpenAICompatibleEmbedder(
        provider="openai-compatible",
        model="custom-model",
        base_url="http://localhost:8080/v1",
    )

    assert embedder.embed([]) == []
    mock_post.assert_not_called()


@pytest.mark.parametrize(
    "response_data,match",
    [
        ({"data": []}, "returned 0 embeddings for 1 texts"),
        ({"data": [{"index": 0}]}, "missing a numeric embedding"),
        (
            {"data": [{"index": 1, "embedding": [0.1, 0.2]}]},
            "invalid embedding indices",
        ),
        (
            {"data": [{"index": 0, "embedding": [0.1, "bad"]}]},
            "missing a numeric embedding",
        ),
    ],
)
@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_rejects_malformed_response(mock_post, response_data, match):
    response = MagicMock()
    response.json.return_value = response_data
    response.raise_for_status = MagicMock()
    mock_post.return_value = response
    embedder = OpenAICompatibleEmbedder(
        provider="openai-compatible",
        model="custom-model",
        base_url="http://localhost:8080/v1",
    )

    with pytest.raises(RuntimeError, match=match):
        embedder.embed(["test"])


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_rejects_inconsistent_dimensions(mock_post):
    mock_post.return_value = _mock_openai_response([[0.1, 0.2], [0.3]])
    embedder = OpenAICompatibleEmbedder(
        provider="openai-compatible",
        model="custom-model",
        base_url="http://localhost:8080/v1",
    )

    with pytest.raises(RuntimeError, match="inconsistent dimensions"):
        embedder.embed(["first", "second"])


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_rejects_configured_dimension_mismatch(mock_post):
    mock_post.return_value = _mock_openai_response([[0.1, 0.2]])
    embedder = OpenAICompatibleEmbedder(
        provider="openai-compatible",
        model="custom-model",
        base_url="http://localhost:8080/v1",
        dimensions=3,
    )

    with pytest.raises(RuntimeError, match="configured for 3 dimensions but returned 2"):
        embedder.embed(["test"])


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_connection_error_raises_without_exposing_api_key(mock_post):
    import requests as req
    mock_post.side_effect = req.ConnectionError()
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1",
        api_key="secret-api-key",
    )

    with pytest.raises(RuntimeError, match="Cannot connect to OpenAI") as exc:
        embedder.embed(["test"])
    assert "secret-api-key" not in str(exc.value)


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_http_error_raises_runtime_error(mock_post):
    import requests as req
    response = MagicMock()
    response.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")
    mock_post.return_value = response
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
    )

    with pytest.raises(RuntimeError, match="OpenAI embedding request failed"):
        embedder.embed(["test"])


@patch("mcp_logseq.vector.embedder.requests.post")
def test_openai_invalid_json_raises_runtime_error(mock_post):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.side_effect = ValueError("invalid JSON")
    mock_post.return_value = response
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
    )

    with pytest.raises(RuntimeError, match="returned invalid JSON"):
        embedder.embed(["test"])


def test_openai_key_includes_configured_dimensions():
    embedder = OpenAICompatibleEmbedder(
        provider="openai",
        model="text-embedding-3-small",
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
        dimensions=512,
    )
    assert embedder.key == "openai/text-embedding-3-small/dimensions=512"


def test_create_embedder_openai():
    config = EmbedderConfig(
        provider="openai",
        model="text-embedding-3-small",
        api_key="test-api-key",
    )
    embedder = create_embedder(config)
    assert isinstance(embedder, OpenAICompatibleEmbedder)
    assert embedder.key == "openai/text-embedding-3-small"


def test_create_embedder_openai_requires_api_key():
    config = EmbedderConfig(
        provider="openai",
        model="text-embedding-3-small",
    )
    with pytest.raises(ValueError, match="requires api_key"):
        create_embedder(config)


def test_create_embedder_openai_compatible():
    config = EmbedderConfig(
        provider="openai-compatible",
        model="custom-model",
        base_url="https://embeddings.example.com/v1",
    )
    embedder = create_embedder(config)
    assert isinstance(embedder, OpenAICompatibleEmbedder)
    assert embedder.key == "openai-compatible/custom-model"
