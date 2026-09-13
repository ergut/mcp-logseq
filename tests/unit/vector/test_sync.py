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


# --- _embed_chunks_batched ---

def test_failed_batch_retries_chunks_individually(tmp_path):
    from types import SimpleNamespace

    def embed(texts):
        if len(texts) > 1:
            raise RuntimeError("400 Bad Request")
        if texts[0] == "bad":
            raise RuntimeError("400 Bad Request")
        return [[0.1, 0.2, 0.3, 0.4]]

    embedder = _make_embedder()
    embedder.embed.side_effect = embed
    engine = SyncEngine(_make_config(str(tmp_path), str(tmp_path / "db")), MagicMock(), MagicMock(), embedder)
    chunks = [SimpleNamespace(text=t, vector=None) for t in ["good", "bad", "also good"]]

    engine._embed_chunks_batched(chunks)

    assert [c.vector is not None for c in chunks] == [True, False, True]


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


def test_sync_aborts_on_dimension_mismatch(tmp_path):
    config = _make_config(str(tmp_path), str(tmp_path / "db"))
    db = MagicMock()
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {},
        SyncMeta(
            embedder_key="ollama/nomic-embed-text",
            dimensions=512,
            last_full_sync=None,
        ),
    )
    embedder = _make_embedder(dims=768)

    engine = SyncEngine(config, db, state_mgr, embedder)
    with pytest.raises(RuntimeError, match="dimensions changed from 512 to 768"):
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


# --- mid-sync file deletion (#91) ---

def _empty_state_mgr() -> MagicMock:
    state_mgr = MagicMock()
    state_mgr.load.return_value = (
        {},
        SyncMeta(embedder_key="ollama/nomic-embed-text", dimensions=4, last_full_sync=None),
    )
    return state_mgr


def test_sync_skips_file_deleted_before_hashing(tmp_path):
    (tmp_path / "page.md").write_text("- Some content for testing here\n")
    engine = SyncEngine(
        _make_config(str(tmp_path), str(tmp_path / "db")), MagicMock(), _empty_state_mgr(), _make_embedder()
    )

    with patch("mcp_logseq.vector.sync._hash_file", side_effect=FileNotFoundError):
        result = engine.sync()

    assert (result.added, result.skipped, result.deleted) == (0, 0, 0)


@pytest.mark.parametrize(
    "previously_indexed, expected_counts",
    [(True, (0, 0, 1)), (False, (0, 0, 0))],
    ids=["existing-file", "new-file"],
)
def test_sync_treats_file_deleted_during_embedding_as_deleted(
    tmp_path, previously_indexed, expected_counts
):
    md = tmp_path / "page.md"
    md.write_text("- Some content for testing here\n")
    db = MagicMock()
    state_mgr = _empty_state_mgr()
    if previously_indexed:
        state_mgr.load.return_value[0]["page.md"] = FileState(
            content_hash="oldhash", last_synced="2024-01-01T00:00:00+00:00", chunk_ids=["page::0"]
        )
    embedder = _make_embedder()

    def embed_then_delete(texts):
        md.unlink()
        return [[0.1, 0.2, 0.3, 0.4]] * len(texts)

    embedder.embed.side_effect = embed_then_delete
    engine = SyncEngine(_make_config(str(tmp_path), str(tmp_path / "db")), db, state_mgr, embedder)

    result = engine.sync()

    assert (result.added, result.updated, result.deleted) == expected_counts
    db.upsert.assert_not_called()
    saved_state = state_mgr.save.call_args[0][0]
    assert "page.md" not in saved_state


# --- _walk_md_files ---

def test_walk_skips_logseq_dir_and_hidden_dirs(tmp_path):
    from mcp_logseq.vector.sync import _walk_md_files

    for rel in ["pages/a.md", "journals/2026_01_01.md", "logseq/bak/pages/a/x.md",
                "logseq/.recycle/pages_a.md", ".trash/b.md", "pages/.hidden/c.md"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("- x")

    found = {str(p.relative_to(tmp_path)) for p in _walk_md_files(str(tmp_path))}

    assert found == {"pages/a.md", "journals/2026_01_01.md"}


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
