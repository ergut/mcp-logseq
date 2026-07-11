"""
Regression tests for asyncio/LanceDB deadlock (issue #44).

Root cause: all ToolHandler.run_tool() implementations are synchronous. Before the
fix, server.py called run_tool() directly in the async event loop, blocking it
entirely. LanceDB's Rust/Arrow layer also caused event-loop contention on Windows
(the to_list() hang could not be reproduced on macOS).

Fix applied: server.py call_tool() now uses ``await asyncio.to_thread(...)`` to
offload all synchronous handler work to a thread pool.

These tests use a real (tiny) LanceDB table and a stub embedder to prove:
  1. VectorDB.get_stats() returns correct page counts after the Arrow-based
     efficiency fix (no more full Python dict conversion per row).
  2. VectorSearchToolHandler.run_tool() completes when dispatched through
     asyncio.to_thread() — i.e. no deadlock even with a live asyncio event loop.
  3. VectorDBStatusToolHandler.run_tool() likewise completes via asyncio.to_thread().
"""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("lancedb", reason="requires the optional 'vector' extra")

from mcp_logseq.vector.db import VectorDB
from mcp_logseq.vector.types import LogseqChunk

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DIMS = 4
_EMBEDDER_KEY = "stub/test-4d"


def _make_chunk(page: str, idx: int, vec: list[float]) -> LogseqChunk:
    return LogseqChunk(
        id=f"{page}::{idx}",
        page=page,
        text=f"content of {page} block {idx}",
        raw=f"raw content {idx}",
        tags=[],
        date=None,
        properties="{}",
        block_index=idx,
        vector=vec,
    )


@pytest.fixture
def tiny_db(tmp_path):
    """Real LanceDB with 3 chunks across 2 pages, plus a sync-meta.json file."""
    db_path = str(tmp_path / "vector_db")

    db = VectorDB.open(db_path, _DIMS)
    chunks = [
        _make_chunk("Page A", 0, [0.1, 0.2, 0.3, 0.4]),
        _make_chunk("Page A", 1, [0.2, 0.3, 0.4, 0.5]),
        _make_chunk("Page B", 0, [0.3, 0.4, 0.5, 0.6]),
    ]
    db.upsert(chunks)
    db.close()

    (tmp_path / "vector_db" / "sync-meta.json").write_text(
        json.dumps(
            {
                "embedder_key": _EMBEDDER_KEY,
                "dimensions": _DIMS,
                "last_full_sync": "2024-01-01T00:00:00+00:00",
            }
        )
    )
    return db_path


def _stub_embedder():
    """Return a MagicMock embedder that returns a fixed 4-d vector."""
    from unittest.mock import MagicMock

    emb = MagicMock()
    emb.key = _EMBEDDER_KEY
    emb.dimensions = _DIMS
    emb.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    return emb


# ---------------------------------------------------------------------------
# 1. get_stats efficiency fix
# ---------------------------------------------------------------------------


class TestGetStats:
    """VectorDB.get_stats() uses Arrow column projection — correct counts, no full scan."""

    def test_returns_correct_chunk_count(self, tiny_db):
        db = VectorDB.open_readonly(tiny_db, _DIMS)
        stats = db.get_stats()
        db.close()
        assert stats["total_chunks"] == 3

    def test_returns_correct_unique_page_count(self, tiny_db):
        db = VectorDB.open_readonly(tiny_db, _DIMS)
        stats = db.get_stats()
        db.close()
        # 3 chunks spread across Page A (2) and Page B (1)
        assert stats["total_pages"] == 2

    def test_returns_zero_for_empty_table(self, tmp_path):
        db_path = str(tmp_path / "empty_db")
        db = VectorDB.open(db_path, _DIMS)
        stats = db.get_stats()
        db.close()
        assert stats["total_chunks"] == 0
        assert stats["total_pages"] == 0


# ---------------------------------------------------------------------------
# 2. asyncio.to_thread regression — VectorSearchToolHandler
# ---------------------------------------------------------------------------


class TestVectorSearchViaToThread:
    """VectorSearchToolHandler.run_tool() must complete when called via asyncio.to_thread()."""

    def test_completes_via_to_thread_no_deadlock(self, tiny_db, tmp_path):
        """Regression: run_tool must not deadlock when dispatched via asyncio.to_thread()."""
        from unittest.mock import MagicMock, patch

        from mcp_logseq.vector.index import VectorSearchToolHandler

        config = MagicMock()
        config.db_path = tiny_db
        config.graph_path = str(tmp_path / "graph")  # non-existent → staleness skips cleanly
        config.embedder = MagicMock()
        handler = VectorSearchToolHandler(config)

        stub = _stub_embedder()

        async def _run():
            with patch("mcp_logseq.vector.index.create_embedder", return_value=stub):
                return await asyncio.to_thread(handler.run_tool, {"query": "hello"})

        results = asyncio.run(_run())
        assert results, "handler returned no TextContent"
        assert results[0].text  # non-empty output

    def test_returns_search_results_via_to_thread(self, tiny_db, tmp_path):
        """Results from a real LanceDB table are returned correctly through the thread boundary."""
        from unittest.mock import MagicMock, patch

        from mcp_logseq.vector.index import VectorSearchToolHandler

        config = MagicMock()
        config.db_path = tiny_db
        config.graph_path = str(tmp_path / "graph")
        config.embedder = MagicMock()
        handler = VectorSearchToolHandler(config)

        stub = _stub_embedder()

        async def _run():
            with patch("mcp_logseq.vector.index.create_embedder", return_value=stub):
                return await asyncio.to_thread(
                    handler.run_tool, {"query": "content", "top_k": 3}
                )

        results = asyncio.run(_run())
        text = results[0].text
        # At least one of our page titles should appear in results
        assert "Page A" in text or "Page B" in text


# ---------------------------------------------------------------------------
# 3. asyncio.to_thread regression — VectorDBStatusToolHandler
# ---------------------------------------------------------------------------


class TestVectorDBStatusViaToThread:
    """VectorDBStatusToolHandler.run_tool() must complete via asyncio.to_thread()."""

    def test_completes_via_to_thread_no_deadlock(self, tiny_db):
        """Regression: status handler must not block or deadlock via asyncio.to_thread()."""
        from unittest.mock import MagicMock

        from mcp_logseq.vector.index import VectorDBStatusToolHandler

        config = MagicMock()
        config.db_path = tiny_db
        config.graph_path = "/nonexistent/graph"
        handler = VectorDBStatusToolHandler(config)

        async def _run():
            return await asyncio.to_thread(handler.run_tool, {})

        results = asyncio.run(_run())
        assert results
        text = results[0].text
        assert "Vector DB Status" in text
        assert "3" in text  # total_chunks
        assert "2" in text  # total_pages
