from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp_logseq.vector.types import FileState, SyncMeta, SyncState

logger = logging.getLogger("mcp-logseq.vector.state")

_STATE_FILE = "sync-state.json"
_META_FILE = "sync-meta.json"

_EMPTY_META = SyncMeta(embedder_key="", dimensions=0, last_full_sync=None)


class StateManager:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._state_path = self._db_path / _STATE_FILE
        self._meta_path = self._db_path / _META_FILE

    def load(self) -> tuple[SyncState, SyncMeta]:
        state = self._load_state()
        meta = self._load_meta()
        return state, meta

    def save(self, state: SyncState, meta: SyncMeta) -> None:
        os.makedirs(self._db_path, exist_ok=True)
        self._save_state(state)
        self._save_meta(meta)

    def _load_state(self) -> SyncState:
        if not self._state_path.exists():
            return {}
        try:
            raw = json.loads(self._state_path.read_text())
            return {
                path: FileState(
                    content_hash=entry["content_hash"],
                    last_synced=entry["last_synced"],
                    chunk_ids=entry["chunk_ids"],
                )
                for path, entry in raw.items()
            }
        except Exception as e:
            logger.warning(f"Could not load sync state, starting fresh: {e}")
            return {}

    def _save_state(self, state: SyncState) -> None:
        raw = {
            path: {
                "content_hash": fs.content_hash,
                "last_synced": fs.last_synced,
                "chunk_ids": fs.chunk_ids,
            }
            for path, fs in state.items()
        }
        self._state_path.write_text(json.dumps(raw, indent=2))

    def _load_meta(self) -> SyncMeta:
        if not self._meta_path.exists():
            return SyncMeta(embedder_key="", dimensions=0, last_full_sync=None)
        try:
            raw = json.loads(self._meta_path.read_text())
            return SyncMeta(
                embedder_key=raw.get("embedder_key", ""),
                dimensions=raw.get("dimensions", 0),
                last_full_sync=raw.get("last_full_sync"),
            )
        except Exception as e:
            logger.warning(f"Could not load sync meta, starting fresh: {e}")
            return SyncMeta(embedder_key="", dimensions=0, last_full_sync=None)

    def _save_meta(self, meta: SyncMeta) -> None:
        raw = {
            "embedder_key": meta.embedder_key,
            "dimensions": meta.dimensions,
            "last_full_sync": meta.last_full_sync,
        }
        self._meta_path.write_text(json.dumps(raw, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
