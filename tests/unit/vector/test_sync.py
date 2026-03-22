from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_logseq.config import EmbedderConfig, VectorConfig
from mcp_logseq.vector.state import StateManager
from mcp_logseq.vector.sync import SyncEngine, check_staleness, _migrate_to_relative_keys
from mcp_logseq.vector.types import FileState, SyncMeta, SyncState


def _make_config(graph_path: str, db_path: str) -> VectorConfig:
    return VectorConfig(
        enabled=True,
        db_path=db_path,
        embedder=EmbedderConfig(provider="ollama", model="nomic-embed-text"),
        graph_path=graph_path,
        include_journals=True,
        exclude_tags=[],
        min_chunk_length=10,
        watch_debounce_ms=5000,
    )


def _make_embedder(dims: int = 4) -> MagicMock:
    embedder = MagicMock()
    embedder.key = "ollama/nomic-embed-text"
    embedder.dimensions = dims
    embedder.embed.return_value = [[0.1, 0.2, 0.3, 0.4]] * 10  # up to 10 vectors
    return embedder


# --- check_staleness ---

def test_staleness_empty_state_with_files(tmp_path):
    (tmp_path / "page.md").write_text("content")
    report = check_staleness(str(tmp_path), {})
    assert report.stale is True
    assert report.changed_count == 1


def test_staleness_no_changes(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("content")

    import hashlib
    file_hash = hashlib.sha256(md.read_bytes()).hexdigest()

    state: SyncState = {
        "page.md": FileState(  # relative key
            content_hash=file_hash,
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["page::0"],
        )
    }
    report = check_staleness(str(tmp_path), state)
    assert report.stale is False
    assert report.changed_count == 0


def test_staleness_detects_deleted_file(tmp_path):
    state: SyncState = {
        "/ghost/page.md": FileState(
            content_hash="abc",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["ghost::0"],
        )
    }
    report = check_staleness(str(tmp_path), state)
    assert report.stale is True
    assert report.deleted_count == 1


def test_staleness_empty_graph_dir(tmp_path):
    report = check_staleness(str(tmp_path), {})
    assert report.stale is False
    assert report.changed_count == 0


def test_staleness_nonexistent_graph_dir():
    report = check_staleness("/nonexistent/path", {})
    assert report.stale is False


def test_staleness_nonexistent_graph_dir_with_state():
    # Container scenario: graph path not mounted but state has indexed entries.
    # Must NOT report stale — would trigger sync that deletes all chunks.
    state: SyncState = {
        "pages/foo.md": FileState(
            content_hash="abc",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["foo::0"],
        )
    }
    report = check_staleness("/nonexistent/path", state)
    assert report.stale is False
    assert report.deleted_count == 0


# --- SyncEngine ---

def test_sync_aborts_when_graph_path_inaccessible(tmp_path):
    # Container scenario: graph path not mounted, state has indexed entries.
    # sync() must return a zero-result and NOT delete any chunks from the DB.
    config = _make_config("/nonexistent/graph/path", str(tmp_path / "db"))
    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {
            "pages/foo.md": FileState(
                content_hash="abc",
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["foo::0", "foo::1"],
            )
        },
        SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None),
    )
    embedder = _make_embedder()

    engine = SyncEngine(config, db, state_mgr, embedder)
    result = engine.sync()

    assert result.added == 0
    assert result.deleted == 0
    db.delete_by_ids.assert_not_called()


def test_sync_aborts_on_embedder_mismatch(tmp_path):
    config = _make_config(str(tmp_path), str(tmp_path / "db"))
    (tmp_path / "page.md").write_text("- Some content here\n")

    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {},
        SyncMeta(
            embedder_key="ollama/different-model",
            dimensions=512,
            last_full_sync=None,
        ),
    )
    embedder = _make_embedder()

    engine = SyncEngine(config, db, state_mgr, embedder)
    with pytest.raises(RuntimeError, match="Embedder changed"):
        engine.sync()


def test_sync_skips_unchanged_files(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("- Some content for testing here\n")

    import hashlib
    file_hash = hashlib.sha256(md.read_bytes()).hexdigest()

    config = _make_config(str(tmp_path), str(tmp_path / "db"))
    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {
            "page.md": FileState(  # relative key
                content_hash=file_hash,
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["page::0"],
            )
        },
        SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None),
    )
    embedder = _make_embedder()

    engine = SyncEngine(config, db, state_mgr, embedder)
    result = engine.sync()

    assert result.skipped == 1
    assert result.added == 0
    embedder.embed.assert_not_called()


def test_sync_deletes_chunks_for_removed_files(tmp_path):
    config = _make_config(str(tmp_path), str(tmp_path / "db"))
    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {
            "/ghost/deleted.md": FileState(
                content_hash="oldhash",
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["deleted::0", "deleted::1"],
            )
        },
        SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None),
    )
    embedder = _make_embedder()

    engine = SyncEngine(config, db, state_mgr, embedder)
    result = engine.sync()

    assert result.deleted == 1
    db.delete_by_ids.assert_called_with(["deleted::0", "deleted::1"])


# --- _migrate_to_relative_keys ---

def test_migrate_no_op_when_already_relative(tmp_path):
    state: SyncState = {
        "pages/foo.md": FileState(
            content_hash="abc",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["foo::0"],
        )
    }
    result, changed = _migrate_to_relative_keys(state, str(tmp_path))
    assert changed is False
    assert result == state


def test_migrate_rewrites_absolute_keys(tmp_path):
    abs_key = str(tmp_path / "pages" / "foo.md")
    state: SyncState = {
        abs_key: FileState(
            content_hash="abc",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["foo::0"],
        )
    }
    result, changed = _migrate_to_relative_keys(state, str(tmp_path))
    assert changed is True
    assert "pages/foo.md" in result
    assert abs_key not in result


def test_migrate_skips_keys_outside_graph_root(tmp_path):
    outside_key = "/other/path/foo.md"
    state: SyncState = {
        outside_key: FileState(
            content_hash="abc",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["foo::0"],
        )
    }
    result, changed = _migrate_to_relative_keys(state, str(tmp_path))
    # Key outside graph root is kept as-is and does NOT set changed=True
    assert outside_key in result
    assert changed is False


def test_sync_migrates_and_saves_legacy_state(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("- Some content for testing here\n")

    import hashlib
    file_hash = hashlib.sha256(md.read_bytes()).hexdigest()
    abs_key = str(md)

    config = _make_config(str(tmp_path), str(tmp_path / "db"))
    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {
            abs_key: FileState(
                content_hash=file_hash,
                last_synced="2024-01-01T00:00:00+00:00",
                chunk_ids=["page::0"],
            )
        },
        SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None),
    )
    embedder = _make_embedder()

    engine = SyncEngine(config, db, state_mgr, embedder)
    result = engine.sync()

    # File is unchanged after migration — should be skipped, not re-embedded
    assert result.skipped == 1
    assert result.added == 0
    embedder.embed.assert_not_called()
    # State was migrated and saved back
    state_mgr.save.assert_called()
