from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

portalocker = pytest.importorskip(
    "portalocker", reason="requires the optional 'vector' extra"
)

from mcp_logseq.bin.logseq_sync import _acquire_sync_lock, _release_sync_lock, _run_sync
from mcp_logseq.config import EmbedderConfig


def test_acquire_and_release_lock(tmp_path):
    lock_file = _acquire_sync_lock(str(tmp_path))
    assert lock_file is not None
    _release_sync_lock(lock_file)
    # Lock file still exists (normal — it's just a sentinel file)
    assert (tmp_path / "sync.lock").exists()


def test_acquire_creates_db_dir(tmp_path):
    db_path = str(tmp_path / "nested" / "db")
    lock_file = _acquire_sync_lock(db_path)
    assert Path(db_path).exists()
    _release_sync_lock(lock_file)


def test_acquire_lock_conflict_raises(tmp_path):
    # Hold the lock from "another process" by locking the file directly
    lock_path = tmp_path / "sync.lock"
    lock_path.touch()
    holder = open(lock_path, "w")
    portalocker.lock(holder, portalocker.LOCK_EX | portalocker.LOCK_NB)

    try:
        with pytest.raises(RuntimeError, match="another sync process is already running"):
            _acquire_sync_lock(str(tmp_path))
    finally:
        portalocker.unlock(holder)
        holder.close()


def test_acquire_calls_portalocker_lock(tmp_path):
    with patch("mcp_logseq.bin.logseq_sync.portalocker") as mock_pl:
        mock_pl.LOCK_EX = portalocker.LOCK_EX
        mock_pl.LOCK_NB = portalocker.LOCK_NB
        mock_pl.LockException = portalocker.LockException
        mock_pl.lock.return_value = None

        lock_file = _acquire_sync_lock(str(tmp_path))
        mock_pl.lock.assert_called_once()
        args = mock_pl.lock.call_args[0]
        assert args[1] == portalocker.LOCK_EX | portalocker.LOCK_NB
        lock_file.close()


def test_release_calls_portalocker_unlock(tmp_path):
    lock_file = _acquire_sync_lock(str(tmp_path))

    with patch("mcp_logseq.bin.logseq_sync.portalocker") as mock_pl:
        mock_pl.unlock.return_value = None
        _release_sync_lock(lock_file)
        mock_pl.unlock.assert_called_once_with(lock_file)


def test_release_swallows_exceptions(tmp_path):
    lock_file = _acquire_sync_lock(str(tmp_path))

    with patch("mcp_logseq.bin.logseq_sync.portalocker") as mock_pl:
        mock_pl.unlock.side_effect = RuntimeError("unexpected")
        # Should not raise
        _release_sync_lock(lock_file)


def test_run_sync_exits_on_lock_conflict(tmp_path, capsys):
    config = SimpleNamespace(db_path=str(tmp_path), graph_path=str(tmp_path), embedder=None)
    with patch("mcp_logseq.bin.logseq_sync._acquire_sync_lock", side_effect=RuntimeError("busy")):
        with pytest.raises(SystemExit) as excinfo:
            _run_sync(config)
    assert excinfo.value.code == 1
    assert "Error: busy" in capsys.readouterr().err


@patch("mcp_logseq.vector.sync.SyncEngine")
@patch("mcp_logseq.vector.state.StateManager")
@patch("mcp_logseq.vector.db.VectorDB")
@patch("mcp_logseq.vector.embedder.create_embedder")
def test_run_sync_prints_selected_provider(
    mock_create_embedder,
    mock_vector_db,
    mock_state_manager,
    mock_sync_engine,
    tmp_path,
    capsys,
):
    embedder = MagicMock()
    embedder.dimensions = 1536
    embedder.key = "openai/text-embedding-3-small"
    mock_create_embedder.return_value = embedder
    mock_sync_engine.return_value.sync.return_value = SimpleNamespace(
        duration_ms=10,
        added=1,
        updated=0,
        deleted=0,
        skipped=0,
    )
    config = SimpleNamespace(
        db_path=str(tmp_path / "db"),
        graph_path=str(tmp_path / "graph"),
        embedder=EmbedderConfig(
            provider="openai",
            model="text-embedding-3-small",
            api_key="test-api-key",
        ),
    )

    _run_sync(config)

    output = capsys.readouterr().out
    assert "Connecting to embedding provider openai (text-embedding-3-small)" in output
    assert "Ollama" not in output
    mock_vector_db.open.assert_called_once_with(str(tmp_path / "db"), 1536)
    mock_state_manager.assert_called_once_with(str(tmp_path / "db"))
