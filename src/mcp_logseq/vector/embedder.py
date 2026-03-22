from __future__ import annotations

import logging
from abc import ABC, abstractmethod

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


def create_embedder(config: EmbedderConfig) -> Embedder:
    if config.provider == "ollama":
        return OllamaEmbedder(model=config.model, base_url=config.base_url)
    raise ValueError(
        f"Unsupported embedder provider: '{config.provider}'. Only 'ollama' is supported."
    )
