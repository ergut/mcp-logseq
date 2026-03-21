"""
Sync engine for Logseq vector database.

Incrementally syncs .md files from the Logseq graph directory into LanceDB.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp_logseq.config import VectorConfig
from mcp_logseq.vector.chunker import chunk_file
from mcp_logseq.vector.db import VectorDB
from mcp_logseq.vector.embedder import Embedder
from mcp_logseq.vector.state import StateManager, now_iso
from mcp_logseq.vector.types import FileState, StalenessReport, SyncMeta, SyncResult, SyncState

logger = logging.getLogger("mcp-logseq.vector.sync")

_EMBED_BATCH_SIZE = 16  # texts per Ollama call


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _walk_md_files(graph_dir: str) -> list[Path]:
    root = Path(graph_dir)
    if not root.exists():
        return []
    return sorted(root.rglob("*.md"))


class SyncEngine:
    def __init__(
        self,
        config: VectorConfig,
        db: VectorDB,
        state_manager: StateManager,
        embedder: Embedder,
    ) -> None:
        self._config = config
        self._db = db
        self._state_mgr = state_manager
        self._embedder = embedder

    def sync(self, rebuild: bool = False) -> SyncResult:
        start = time.monotonic()

        if rebuild:
            self._rebuild_db()
            # Reopen DB after directory was deleted — old connection has stale schema
            self._db = VectorDB.open(self._config.db_path, self._embedder.dimensions)

        state, meta = self._state_mgr.load()

        # Embedder mismatch check
        if meta.embedder_key and meta.embedder_key != self._embedder.key:
            raise RuntimeError(
                f"Embedder changed from '{meta.embedder_key}' to '{self._embedder.key}'. "
                f"Run sync_vector_db with rebuild=true to re-index from scratch."
            )

        md_files = _walk_md_files(self._config.graph_path)
        if not md_files:
            logger.warning(f"No .md files found in {self._config.graph_path}")

        # Identify what needs processing — keys are relative paths for cross-mount portability
        graph_root = Path(self._config.graph_path)
        current_paths = {str(f.relative_to(graph_root)): f for f in md_files}
        added = updated = deleted = skipped = 0

        # Collect all chunks to embed in batches
        files_to_process: list[tuple[str, Path]] = []
        for path_str, file_path in current_paths.items():
            file_hash = _hash_file(file_path)
            if path_str in state and state[path_str].content_hash == file_hash:
                skipped += 1
                continue
            files_to_process.append((path_str, file_path))

        # Delete chunks for changed and deleted files
        for path_str in files_to_process:
            path_str_key = path_str[0]
            if path_str_key in state:
                self._db.delete_by_ids(state[path_str_key].chunk_ids)
                updated += 1
            else:
                added += 1

        # Handle deleted files
        deleted_paths = set(state.keys()) - set(current_paths.keys())
        for path_str in deleted_paths:
            self._db.delete_by_ids(state[path_str].chunk_ids)
            del state[path_str]
            deleted += 1

        # Process changed/new files in batches
        all_chunks_by_file: dict[str, list] = {}
        for path_str, file_path in files_to_process:
            chunks = chunk_file(file_path, self._config)
            all_chunks_by_file[path_str] = chunks

        # Embed in batches across all files
        all_chunks_flat = [c for chunks in all_chunks_by_file.values() for c in chunks]
        if all_chunks_flat:
            self._embed_chunks_batched(all_chunks_flat)

        # Upsert into DB and update state
        for path_str, file_path in files_to_process:
            chunks = all_chunks_by_file[path_str]
            embedded = [c for c in chunks if c.vector is not None]
            if embedded:
                self._db.upsert(embedded)

            file_hash = _hash_file(file_path)
            state[path_str] = FileState(
                content_hash=file_hash,
                last_synced=now_iso(),
                chunk_ids=[c.id for c in chunks],
            )

        # Rebuild FTS index after sync
        if files_to_process or deleted_paths:
            self._db.create_fts_index()

        meta = SyncMeta(
            embedder_key=self._embedder.key,
            dimensions=self._embedder.dimensions,
            last_full_sync=now_iso(),
        )
        self._state_mgr.save(state, meta)

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            f"Sync complete: +{added} new, ~{updated} updated, -{deleted} deleted, "
            f"{skipped} skipped in {duration_ms}ms"
        )
        return SyncResult(
            added=added,
            updated=updated,
            deleted=deleted,
            skipped=skipped,
            duration_ms=duration_ms,
        )

    def _embed_chunks_batched(self, chunks: list) -> None:
        texts = [c.text for c in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i:i + _EMBED_BATCH_SIZE]
            try:
                batch_vectors = self._embedder.embed(batch)
                vectors.extend(batch_vectors)
            except Exception as e:
                logger.warning(f"Embedding batch {i//  _EMBED_BATCH_SIZE} failed: {e} — skipping {len(batch)} chunks")
                vectors.extend([None] * len(batch))  # type: ignore[list-item]

        for chunk, vector in zip(chunks, vectors):
            chunk.vector = vector

    def _rebuild_db(self) -> None:
        logger.info("Rebuild requested — dropping existing DB and state")
        db_path = Path(self._config.db_path)
        if db_path.exists():
            shutil.rmtree(db_path)
            logger.info(f"Removed {db_path}")
        os.makedirs(db_path, exist_ok=True)


def check_staleness(graph_dir: str, state: SyncState) -> StalenessReport:
    """
    Fast staleness check — hashes files only, no DB or network calls.
    Returns a StalenessReport indicating how many files have changed since last sync.
    """
    md_files = _walk_md_files(graph_dir)
    graph_root = Path(graph_dir)
    current_paths = {str(f.relative_to(graph_root)): f for f in md_files}

    changed = 0
    for path_str, file_path in current_paths.items():
        if path_str not in state:
            changed += 1
            continue
        try:
            file_hash = _hash_file(file_path)
            if file_hash != state[path_str].content_hash:
                changed += 1
        except Exception:
            changed += 1

    deleted_count = len(set(state.keys()) - set(current_paths.keys()))

    last_sync: str | None = None
    if state:
        synced_times = [fs.last_synced for fs in state.values() if fs.last_synced]
        if synced_times:
            last_sync = max(synced_times)

    stale = changed > 0 or deleted_count > 0
    return StalenessReport(
        stale=stale,
        changed_count=changed,
        deleted_count=deleted_count,
        last_sync=last_sync,
    )
