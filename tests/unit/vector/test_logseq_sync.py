from pathlib import Path
from unittest.mock import MagicMock, patch

import portalocker
import pytest

from mcp_logseq.bin.logseq_sync import _acquire_sync_lock, _release_sync_lock


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


def test_acquire_lock_conflict_exits(tmp_path, capsys):
    # Hold the lock from "another process" by locking the file directly
    lock_path = tmp_path / "sync.lock"
    lock_path.touch()
    holder = open(lock_path, "w")
    portalocker.lock(holder, portalocker.LOCK_EX | portalocker.LOCK_NB)

    try:
        with patch("sys.exit") as mock_exit:
            _acquire_sync_lock(str(tmp_path))
            mock_exit.assert_called_once_with(1)

        captured = capsys.readouterr()
        assert "another sync process is already running" in captured.err
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
