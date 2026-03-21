import json
from pathlib import Path

import pytest

from mcp_logseq.vector.state import StateManager, now_iso
from mcp_logseq.vector.types import FileState, SyncMeta


def test_load_returns_empty_when_no_files(tmp_path):
    mgr = StateManager(str(tmp_path / "db"))
    state, meta = mgr.load()
    assert state == {}
    assert meta.embedder_key == ""
    assert meta.dimensions == 0
    assert meta.last_full_sync is None


def test_save_and_reload(tmp_path):
    db_path = tmp_path / "db"
    mgr = StateManager(str(db_path))

    state = {
        "/path/to/page.md": FileState(
            content_hash="abc123",
            last_synced="2024-01-01T00:00:00+00:00",
            chunk_ids=["Page::0", "Page::1"],
        )
    }
    meta = SyncMeta(
        embedder_key="ollama/nomic-embed-text",
        dimensions=768,
        last_full_sync="2024-01-01T00:00:00+00:00",
    )

    mgr.save(state, meta)

    mgr2 = StateManager(str(db_path))
    loaded_state, loaded_meta = mgr2.load()

    assert "/path/to/page.md" in loaded_state
    fs = loaded_state["/path/to/page.md"]
    assert fs.content_hash == "abc123"
    assert fs.chunk_ids == ["Page::0", "Page::1"]

    assert loaded_meta.embedder_key == "ollama/nomic-embed-text"
    assert loaded_meta.dimensions == 768
    assert loaded_meta.last_full_sync == "2024-01-01T00:00:00+00:00"


def test_save_creates_db_directory(tmp_path):
    db_path = tmp_path / "nested" / "db"
    mgr = StateManager(str(db_path))
    mgr.save({}, SyncMeta(embedder_key="x", dimensions=1, last_full_sync=None))
    assert db_path.exists()


def test_load_handles_corrupted_state_file(tmp_path):
    db_path = tmp_path / "db"
    db_path.mkdir()
    (db_path / "sync-state.json").write_text("{ invalid json }")

    mgr = StateManager(str(db_path))
    state, _ = mgr.load()
    assert state == {}


def test_load_handles_corrupted_meta_file(tmp_path):
    db_path = tmp_path / "db"
    db_path.mkdir()
    (db_path / "sync-meta.json").write_text("not json at all")

    mgr = StateManager(str(db_path))
    _, meta = mgr.load()
    assert meta.embedder_key == ""


def test_now_iso_format():
    ts = now_iso()
    # Should be a valid ISO timestamp ending with +00:00 (UTC)
    assert "T" in ts
    assert "+" in ts or "Z" in ts
