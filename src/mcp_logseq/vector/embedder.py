from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import requests

from mcp_logseq.config import EmbedderConfig

logger = logging.getLogger("mcp-logseq.vector.embedder")


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per text."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...

    @property
    @abstractmethod
    def key(self) -> str:
        """Unique identifier for this embedder, e.g. 'ollama/nomic-embed-text'."""
        ...


class OllamaEmbedder(Embedder):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dimensions: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        url = f"{self._base_url}/api/embed"
        try:
            response = requests.post(
                url,
                json={"model": self._model, "input": texts},
                timeout=120,
            )
            response.raise_for_status()
        except requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base_url}. Is Ollama running?"
            )
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama embedding request failed: {e}")

        data = response.json()
        vectors: list[list[float]] = data.get("embeddings", [])

        if not vectors:
            raise RuntimeError(f"Ollama returned no embeddings for {len(texts)} texts")

        # Cache dimensions on first successful call
        if self._dimensions is None:
            self._dimensions = len(vectors[0])
            logger.debug(f"OllamaEmbedder dimensions detected: {self._dimensions}")

        return vectors

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            # Probe with a single text to detect dimensions
            self.embed(["probe"])
        return self._dimensions  # type: ignore[return-value]

    @property
    def key(self) -> str:
        return f"ollama/{self._model}"


class OpenAICompatibleEmbedder(Embedder):
    """Embed through an OpenAI-compatible ``POST /embeddings`` endpoint."""

    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._requested_dimensions = dimensions
        self._dimensions = dimensions

    @property
    def _display_name(self) -> str:
        return "OpenAI" if self._provider == "openai" else "OpenAI-compatible"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        if self._requested_dimensions is not None:
            payload["dimensions"] = self._requested_dimensions

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = requests.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
        except requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to {self._display_name} embedding API at "
                f"{self._base_url}."
            )
        except requests.Timeout:
            raise RuntimeError(
                f"{self._display_name} embedding request timed out at {self._base_url}."
            )
        except requests.HTTPError as e:
            raise RuntimeError(f"{self._display_name} embedding request failed: {e}")
        except requests.RequestException as e:
            raise RuntimeError(
                f"{self._display_name} embedding request failed: {e}"
            )

        try:
            data = response.json()
        except ValueError as e:
            raise RuntimeError(
                f"{self._display_name} embedding API returned invalid JSON"
            ) from e

        vectors = self._parse_vectors(data, len(texts))
        detected_dimensions = len(vectors[0])
        if (
            self._requested_dimensions is not None
            and detected_dimensions != self._requested_dimensions
        ):
            raise RuntimeError(
                f"{self._display_name} embedder was configured for "
                f"{self._requested_dimensions} dimensions but returned "
                f"{detected_dimensions}"
            )
        self._dimensions = detected_dimensions
        logger.debug(
            f"OpenAICompatibleEmbedder dimensions detected: {self._dimensions}"
        )
        return vectors

    def _parse_vectors(self, data: object, expected_count: int) -> list[list[float]]:
        if not isinstance(data, dict):
            raise RuntimeError(
                f"{self._display_name} embedding API returned an invalid response"
            )
        items = data.get("data")
        if not isinstance(items, list):
            raise RuntimeError(
                f"{self._display_name} embedding API returned an invalid response"
            )
        if len(items) != expected_count:
            raise RuntimeError(
                f"{self._display_name} returned {len(items)} embeddings for "
                f"{expected_count} texts"
            )

        indexed_vectors: list[tuple[int, list[float]]] = []
        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(
                    f"{self._display_name} response item is missing a numeric embedding"
                )
            index = item.get("index")
            vector = item.get("embedding")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not isinstance(vector, list)
                or not vector
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in vector
                )
            ):
                raise RuntimeError(
                    f"{self._display_name} response item is missing a numeric embedding"
                )
            indexed_vectors.append((index, [float(value) for value in vector]))

        indexed_vectors.sort(key=lambda item: item[0])
        if [item[0] for item in indexed_vectors] != list(range(expected_count)):
            raise RuntimeError(
                f"{self._display_name} response contains invalid embedding indices"
            )

        vectors = [item[1] for item in indexed_vectors]
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise RuntimeError(
                f"{self._display_name} returned embeddings with inconsistent dimensions"
            )
        return vectors

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self.embed(["probe"])
        return self._dimensions  # type: ignore[return-value]

    @property
    def key(self) -> str:
        key = f"{self._provider}/{self._model}"
        if self._requested_dimensions is not None:
            key += f"/dimensions={self._requested_dimensions}"
        return key


def create_embedder(config: EmbedderConfig) -> Embedder:
    if config.provider == "ollama":
        return OllamaEmbedder(
            model=config.model,
            base_url=config.base_url or "http://localhost:11434",
        )
    if config.provider in {"openai", "openai-compatible"}:
        if config.provider == "openai" and not config.api_key:
            raise ValueError("Embedder provider 'openai' requires api_key")
        base_url = config.base_url
        if not base_url and config.provider == "openai":
            base_url = "https://api.openai.com/v1"
        if not base_url:
            raise ValueError(
                f"Embedder provider '{config.provider}' requires base_url"
            )
        return OpenAICompatibleEmbedder(
            provider=config.provider,
            model=config.model,
            base_url=base_url,
            api_key=config.api_key,
            dimensions=config.dimensions,
        )
    raise ValueError(
        f"Unsupported embedder provider: '{config.provider}'. "
        "Supported providers: ollama, openai, openai-compatible."
    )
