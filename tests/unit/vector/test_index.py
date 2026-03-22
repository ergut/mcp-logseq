"""Unit tests for read-only vector tool handlers in vector/index.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mcp_logseq.vector.index import (
    VectorDBStatusToolHandler,
    VectorSearchToolHandler,
    SyncVectorDBToolHandler,
    _check_watcher_running,
)


def _make_config():
    config = MagicMock()
    config.db_path = "/tmp/test-vector-db"
    config.graph_path = "/tmp/test-graph"
    return config


def _make_meta():
    meta = MagicMock()
    meta.embedder_key = "ollama/qwen3-embedding:4b"
    meta.dimensions = 2560
    return meta


def _make_stale_report(changed=2, deleted=0):
    report = MagicMock()
    report.stale = True
    report.changed_count = changed
    report.deleted_count = deleted
    return report


def _make_fresh_report():
    report = MagicMock()
    report.stale = False
    return report


class TestVectorSearchReadOnly:
    """vector_search is read-only — no writes, no background sync."""

    def test_search_returns_staleness_note_without_syncing(self):
        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_stale_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 2560]
            mock_db.open_readonly.return_value.search.return_value = []

            results = handler.run_tool({"query": "test"})

            # Should report staleness but NOT trigger any sync
            assert "2 pages changed since last sync" in results[0].text
            assert "sync_vector_db" in results[0].text
            # Should NOT call save (no migration, no sync)
            mock_sm.return_value.save.assert_not_called()

    def test_search_no_prefix_when_fresh(self):
        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 2560]
            mock_db.open_readonly.return_value.search.return_value = []

            results = handler.run_tool({"query": "test"})
            assert "Note:" not in results[0].text

    def test_search_uses_open_readonly(self):
        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 2560]
            mock_db.open_readonly.return_value.search.return_value = []

            handler.run_tool({"query": "test"})

            # Must use open_readonly, never open
            mock_db.open_readonly.assert_called_once()
            mock_db.open.assert_not_called()

    def test_search_shows_error_when_db_not_initialized(self):
        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 2560]
            mock_db.open_readonly.side_effect = RuntimeError("Vector DB not initialized.")

            results = handler.run_tool({"query": "test"})
            assert "not initialized" in results[0].text

    def test_search_never_calls_state_save(self):
        config = _make_config()
        handler = VectorSearchToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.create_embedder") as mock_emb,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_emb.return_value.embed.return_value = [[0.1] * 2560]
            mock_db.open_readonly.return_value.search.return_value = []

            handler.run_tool({"query": "test"})
            mock_sm.return_value.save.assert_not_called()


class TestSyncVectorDBSubprocess:
    """sync_vector_db delegates to logseq-sync subprocess."""

    def test_sync_calls_subprocess_once(self):
        config = _make_config()
        handler = SyncVectorDBToolHandler(config)

        with patch("mcp_logseq.vector.index.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0,
                stdout="Done in 100ms: +5 added, ~2 updated, -1 deleted, 10 skipped",
                stderr="",
            )

            results = handler.run_tool({})

            call_args = mock_sub.run.call_args
            cmd = call_args[0][0]
            assert "--once" in cmd
            assert "--rebuild" not in cmd
            assert "Done in 100ms" in results[0].text

    def test_sync_calls_subprocess_rebuild(self):
        config = _make_config()
        handler = SyncVectorDBToolHandler(config)

        with patch("mcp_logseq.vector.index.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0,
                stdout="Done in 5000ms: +100 added, ~0 updated, -0 deleted, 0 skipped",
                stderr="",
            )

            results = handler.run_tool({"rebuild": True})

            call_args = mock_sub.run.call_args
            cmd = call_args[0][0]
            assert "--rebuild" in cmd
            assert "--once" not in cmd

    def test_sync_reports_subprocess_failure(self):
        config = _make_config()
        handler = SyncVectorDBToolHandler(config)

        with patch("mcp_logseq.vector.index.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: Embedder changed from 'x' to 'y'",
            )

            results = handler.run_tool({})
            assert "Sync failed" in results[0].text
            assert "Embedder changed" in results[0].text

    def test_sync_reports_timeout(self):
        import subprocess
        config = _make_config()
        handler = SyncVectorDBToolHandler(config)

        with patch("mcp_logseq.vector.index.subprocess") as mock_sub:
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="logseq-sync", timeout=600)

            results = handler.run_tool({})
            assert "timed out" in results[0].text


class TestVectorDBStatusReadOnly:
    """vector_db_status is read-only — no writes."""

    def test_status_uses_open_readonly(self):
        config = _make_config()
        handler = VectorDBStatusToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_db.open_readonly.return_value.get_stats.return_value = {"total_chunks": 100, "total_pages": 10}

            handler.run_tool({})

            mock_db.open_readonly.assert_called_once()
            mock_db.open.assert_not_called()

    def test_status_never_calls_state_save(self):
        config = _make_config()
        handler = VectorDBStatusToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_db.open_readonly.return_value.get_stats.return_value = {"total_chunks": 100, "total_pages": 10}

            handler.run_tool({})
            mock_sm.return_value.save.assert_not_called()

    def test_status_shows_watcher_status(self):
        config = _make_config()
        handler = VectorDBStatusToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.check_staleness", return_value=_make_fresh_report()),
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
            patch("mcp_logseq.vector.index._check_watcher_running", return_value="not running"),
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_db.open_readonly.return_value.get_stats.return_value = {"total_chunks": 100, "total_pages": 10}

            results = handler.run_tool({})
            assert "Watcher:" in results[0].text
            assert "not running" in results[0].text

    def test_status_shows_version_mismatch_error(self):
        config = _make_config()
        handler = VectorDBStatusToolHandler(config)

        with (
            patch("mcp_logseq.vector.index.StateManager") as mock_sm,
            patch("mcp_logseq.vector.index.VectorDB") as mock_db,
        ):
            mock_sm.return_value.load.return_value = ({}, _make_meta())
            mock_db.open_readonly.side_effect = RuntimeError(
                "Vector DB data exists but cannot be read. Possible LanceDB version mismatch."
            )

            results = handler.run_tool({})
            assert "version mismatch" in results[0].text


class TestCheckWatcherRunning:
    def test_returns_not_running_when_no_pid_file(self, tmp_path):
        assert _check_watcher_running(str(tmp_path)) == "not running"

    def test_returns_not_running_when_stale_pid(self, tmp_path):
        pid_file = tmp_path / "sync.pid"
        pid_file.write_text("99999999")  # PID that almost certainly doesn't exist
        assert _check_watcher_running(str(tmp_path)) == "not running"

    def test_returns_running_for_current_pid(self, tmp_path):
        import os
        pid_file = tmp_path / "sync.pid"
        pid_file.write_text(str(os.getpid()))  # current process is always alive
        result = _check_watcher_running(str(tmp_path))
        assert result.startswith("running (PID")
