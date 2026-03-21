from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogseqChunk:
    id: str                         # "{page}::{block_index}"
    page: str                       # page title
    text: str                       # cleaned text for embedding
    raw: str                        # original block content
    tags: list[str]
    date: str | None                # YYYY-MM-DD or None
    properties: str                 # JSON blob of page-level properties
    block_index: int
    vector: list[float] | None = None


@dataclass
class FileState:
    content_hash: str
    last_synced: str                # ISO timestamp
    chunk_ids: list[str]


# SyncState maps file path → FileState
SyncState = dict[str, FileState]


@dataclass
class SyncMeta:
    embedder_key: str               # e.g. "ollama/nomic-embed-text"
    dimensions: int
    last_full_sync: str | None


@dataclass
class SearchResult:
    page: str
    text: str
    raw: str
    score: float
    tags: list[str]
    date: str | None
    properties: dict[str, Any]
    chunk_index: int


@dataclass
class StalenessReport:
    stale: bool
    changed_count: int
    deleted_count: int
    last_sync: str | None


@dataclass
class SyncResult:
    added: int
    updated: int
    deleted: int
    skipped: int
    duration_ms: int


@dataclass
class SearchParams:
    query_text: str
    query_vector: list[float]
    top_k: int = 5
    filter_tags: list[str] | None = None
    filter_page: str | None = None
    mode: str = "hybrid"            # "hybrid" | "vector" | "keyword"
