"""Unit tests for BackgroundSyncer and auto-sync behavior in vector/index.py."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

from mcp_logseq.vector.index import BackgroundSyncer
from mcp_logseq.vector.types import SyncResult


def _make_config():
    config = MagicMock()
    config.db_path = "/tmp/test-vector-db"
    config.graph_path = "/tmp/test-graph"
    return config


def _make_sync_result(added=1):
    return SyncResult(added=added, updated=0, deleted=0, skipped=0, duration_ms=100)


class TestBackgroundSyncer:
    def test_trigger_starts_sync_and_returns_true(self):
        syncer = BackgroundSyncer()
        config = _make_config()
        completed = threading.Event()

        def fake_run(cfg):
            completed.set()

        syncer._run = fake_run
        result = syncer.trigger(config)
        assert result is True
        completed.wait(timeout=2)

    def test_trigger_returns_false_while_running(self):
        syncer = BackgroundSyncer()
        config = _make_config()
        # Hold the lock manually to simulate an in-progress sync
        syncer._lock.acquire()
        try:
            assert syncer.is_running is True
            assert syncer.trigger(config) is False
        finally:
            syncer._lock.release()

    def test_is_running_false_initially(self):
        syncer = BackgroundSyncer()
        assert syncer.is_running is False

    def test_releases_lock_after_success(self):
        syncer = BackgroundSyncer()
        config = _make_config()
        done = threading.Event()

        with (
            patch("mcp_logseq.vector.index.create_embedder") as mock_embedder,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch("mcp_logseq.vector.index.StateManager"),
            patch("mcp_logseq.vector.index.SyncEngine") as mock_engine,
        ):
            mock_embedder.return_value.dimensions = 4
            mock_engine.return_value.sync.return_value = _make_sync_result()
            mock_db.open.return_value = MagicMock()

            syncer.trigger(config)
            # Poll until lock is released
            for _ in range(20):
                if not syncer.is_running:
                    break
                time.sleep(0.1)

        assert syncer.is_running is False

    def test_releases_lock_after_error(self):
        syncer = BackgroundSyncer()
        config = _make_config()

        with patch("mcp_logseq.vector.index.create_embedder", side_effect=RuntimeError("boom")):
            syncer.trigger(config)
            for _ in range(20):
                if not syncer.is_running:
                    break
                time.sleep(0.1)

        assert syncer.is_running is False
        assert "boom" in syncer._last_error

    def test_second_trigger_succeeds_after_first_completes(self):
        syncer = BackgroundSyncer()
        config = _make_config()

        with (
            patch("mcp_logseq.vector.index.create_embedder") as mock_embedder,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch("mcp_logseq.vector.index.StateManager"),
            patch("mcp_logseq.vector.index.SyncEngine") as mock_engine,
        ):
            mock_embedder.return_value.dimensions = 4
            mock_engine.return_value.sync.return_value = _make_sync_result()
            mock_db.open.return_value = MagicMock()

            assert syncer.trigger(config) is True
            for _ in range(20):
                if not syncer.is_running:
                    break
                time.sleep(0.1)

            assert syncer.trigger(config) is True


class TestVectorSearchAutoSync:
    """Test that vector_search triggers background sync on staleness."""

    def _make_stale_report(self, changed=2, deleted=0):
        report = MagicMock()
        report.stale = True
        report.changed_count = changed
        report.deleted_count = deleted
        return report

    def _make_fresh_report(self):
        report = MagicMock()
        report.stale = False
        return report

    def _make_meta(self):
        meta = MagicMock()
        meta.embedder_key = "ollama/qwen3-embedding:8b"
        meta.dimensions = 4096
        return meta

    def test_search_triggers_sync_when_stale(self):
        from mcp_logseq.vector.index import VectorSearchToolHandler, _syncer

        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=self._make_stale_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch.object(_syncer, "trigger", return_value=True) as mock_trigger,
        ):
            mock_sm.return_value.load.return_value = (MagicMock(), self._make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 4096]
            mock_db.open.return_value.search.return_value = []

            results = handler.run_tool({"query": "test"})
            mock_trigger.assert_called_once_with(config)
            assert "background sync started" in results[0].text

    def test_search_notes_sync_in_progress(self):
        from mcp_logseq.vector.index import VectorSearchToolHandler, _syncer

        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=self._make_stale_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch.object(_syncer, "trigger", return_value=False),
        ):
            mock_sm.return_value.load.return_value = (MagicMock(), self._make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 4096]
            mock_db.open.return_value.search.return_value = []

            results = handler.run_tool({"query": "test"})
            assert "already in progress" in results[0].text

    def test_search_no_prefix_when_fresh(self):
        from mcp_logseq.vector.index import VectorSearchToolHandler, _syncer

        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=self._make_fresh_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch.object(_syncer, "trigger") as mock_trigger,
        ):
            mock_sm.return_value.load.return_value = (MagicMock(), self._make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 4096]
            mock_db.open.return_value.search.return_value = []

            results = handler.run_tool({"query": "test"})
            mock_trigger.assert_not_called()
            assert "Note:" not in results[0].text


class TestStateMigrationInToolHandlers:
    """Test that tool handlers migrate absolute-path state keys on load."""

    def _make_meta(self):
        from mcp_logseq.vector.types import SyncMeta
        return SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None)

    def _make_absolute_state(self, graph_path="/tmp/test-graph"):
        from mcp_logseq.vector.types import FileState
        return {
            f"{graph_path}/pages/foo.md": FileState(
                content_hash="abc",
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["foo::0"],
            ),
            f"{graph_path}/journals/2024_01_01.md": FileState(
                content_hash="def",
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["journal::0"],
            ),
        }

    def test_search_migrates_absolute_state_keys(self):
        from mcp_logseq.vector.index import VectorSearchToolHandler, _syncer

        config = _make_config()
        handler = VectorSearchToolHandler(config)
        abs_state = self._make_absolute_state(config.graph_path)
        meta = self._make_meta()

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness") as mock_stale,
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch.object(_syncer, "trigger", return_value=False),
        ):
            mock_sm_inst = mock_sm.return_value
            mock_sm_inst.load.return_value = (abs_state, meta)
            mock_stale.return_value = MagicMock(stale=False)
            mock_emb.return_value.embed.return_value = [[0.1] * 4]
            mock_db.open.return_value.search.return_value = []

            handler.run_tool({"query": "test"})

            # State should have been saved back with migrated keys
            mock_sm_inst.save.assert_called_once()
            saved_state = mock_sm_inst.save.call_args[0][0]
            assert "pages/foo.md" in saved_state
            assert "journals/2024_01_01.md" in saved_state
            assert f"{config.graph_path}/pages/foo.md" not in saved_state

    def test_status_migrates_absolute_state_keys(self):
        from mcp_logseq.vector.index import VectorDBStatusToolHandler

        config = _make_config()
        handler = VectorDBStatusToolHandler(config)
        abs_state = self._make_absolute_state(config.graph_path)
        meta = self._make_meta()

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness") as mock_stale,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm_inst = mock_sm.return_value
            mock_sm_inst.load.return_value = (abs_state, meta)
            mock_stale.return_value = MagicMock(stale=False)
            mock_db.open.return_value.get_stats.return_value = {"total_chunks": 100, "total_pages": 10}

            handler.run_tool({})

            # State should have been saved back with migrated keys
            mock_sm_inst.save.assert_called_once()
            saved_state = mock_sm_inst.save.call_args[0][0]
            assert "pages/foo.md" in saved_state

    def test_search_skips_save_when_already_relative(self):
        from mcp_logseq.vector.index import VectorSearchToolHandler, _syncer
        from mcp_logseq.vector.types import FileState

        config = _make_config()
        handler = VectorSearchToolHandler(config)
        relative_state = {
            "pages/foo.md": FileState(
                content_hash="abc",
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["foo::0"],
            )
        }
        meta = self._make_meta()

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness") as mock_stale,
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch.object(_syncer, "trigger", return_value=False),
        ):
            mock_sm_inst = mock_sm.return_value
            mock_sm_inst.load.return_value = (relative_state, meta)
            mock_stale.return_value = MagicMock(stale=False)
            mock_emb.return_value.embed.return_value = [[0.1] * 4]
            mock_db.open.return_value.search.return_value = []

            handler.run_tool({"query": "test"})

            # No migration needed — save should NOT be called
            mock_sm_inst.save.assert_not_called()
