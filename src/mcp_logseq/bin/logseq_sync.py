"""
logseq-sync CLI — sync Logseq notes into the vector database.

Usage:
  logseq-sync --once       Run incremental sync and exit
  logseq-sync --watch      Run sync then watch for file changes
  logseq-sync --rebuild    Drop DB and re-index everything from scratch
  logseq-sync --status     Show staleness report without syncing

Requires LOGSEQ_CONFIG_FILE env var pointing to a config JSON file
with vector.enabled set to true.

This CLI is the single writer for the vector DB. The MCP server delegates
all sync operations here via subprocess to enforce the single-writer principle.
"""

from __future__ import annotations

import argparse
import atexit
import fcntl
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _load_config():
    from mcp_logseq.config import load_vector_config
    config = load_vector_config()
    if config is None:
        print(
            "Error: LOGSEQ_CONFIG_FILE is not set or vector.enabled is not true.\n"
            "Set LOGSEQ_CONFIG_FILE to a config JSON with vector.enabled=true.",
            file=sys.stderr,
        )
        sys.exit(1)
    return config


def _acquire_sync_lock(db_path: str):
    """Acquire an inter-process file lock. Returns the lock file object (keep it open)."""
    os.makedirs(db_path, exist_ok=True)
    lock_path = Path(db_path) / "sync.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except OSError:
        lock_file.close()
        print(
            "Error: another sync process is already running. "
            "Wait for it to finish or check for stale sync.lock.",
            file=sys.stderr,
        )
        sys.exit(1)


def _release_sync_lock(lock_file):
    """Release the inter-process file lock."""
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass


def _write_pid(db_path: str) -> None:
    """Write PID file so MCP server can check if watcher is running."""
    pid_path = Path(db_path) / "sync.pid"
    pid_path.write_text(str(os.getpid()))


def _remove_pid(db_path: str) -> None:
    """Remove PID file on exit."""
    pid_path = Path(db_path) / "sync.pid"
    pid_path.unlink(missing_ok=True)


def _run_sync(config, rebuild: bool = False) -> None:
    from mcp_logseq.vector.db import VectorDB
    from mcp_logseq.vector.embedder import create_embedder
    from mcp_logseq.vector.state import StateManager
    from mcp_logseq.vector.sync import SyncEngine

    print(f"Connecting to Ollama ({config.embedder.model})...")
    try:
        embedder = create_embedder(config.embedder)
        dimensions = embedder.dimensions
        print(f"Embedder ready: {embedder.key} ({dimensions} dims)")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    lock_file = _acquire_sync_lock(config.db_path)
    try:
        db = VectorDB.open(config.db_path, dimensions)
        state_mgr = StateManager(config.db_path)
        engine = SyncEngine(config, db, state_mgr, embedder)

        action = "Rebuilding" if rebuild else "Syncing"
        print(f"{action} {config.graph_path} → {config.db_path}")

        try:
            result = engine.sync(rebuild=rebuild)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            db.close()
            sys.exit(1)

        db.close()
    finally:
        _release_sync_lock(lock_file)

    print(
        f"Done in {result.duration_ms}ms: "
        f"+{result.added} added, "
        f"~{result.updated} updated, "
        f"-{result.deleted} deleted, "
        f"{result.skipped} skipped"
    )


def _show_status(config) -> None:
    from mcp_logseq.vector.state import StateManager
    from mcp_logseq.vector.sync import check_staleness

    state_mgr = StateManager(config.db_path)
    state, meta = state_mgr.load()

    if not meta.embedder_key:
        print("Vector DB: not initialized (run --once first)")
        return

    report = check_staleness(config.graph_path, state)

    print(f"Embedder:    {meta.embedder_key}")
    print(f"Dimensions:  {meta.dimensions}")
    print(f"Last sync:   {meta.last_full_sync or 'never'}")
    print(f"Pages synced: {len(state)}")

    if report.stale:
        print(
            f"Status:      OUT OF DATE "
            f"({report.changed_count} changed, {report.deleted_count} deleted)"
        )
    else:
        print("Status:      up to date")


def _watch(config) -> None:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print(
            "Error: watchdog is not installed. Run: uv sync --extra vector",
            file=sys.stderr,
        )
        sys.exit(1)

    debounce_s = config.watch_debounce_ms / 1000
    last_event_time: list[float] = [0.0]
    pending: list[bool] = [False]

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            if not str(event.src_path).endswith(".md"):
                return
            last_event_time[0] = time.monotonic()
            pending[0] = True

    # Initial sync
    _run_sync(config)

    # Write PID file so MCP server can report watcher status
    _write_pid(config.db_path)
    atexit.register(_remove_pid, config.db_path)

    print(f"Watching {config.graph_path} (debounce: {config.watch_debounce_ms}ms)...")

    observer = Observer()
    observer.schedule(Handler(), config.graph_path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(0.5)
            if pending[0] and (time.monotonic() - last_event_time[0]) >= debounce_s:
                pending[0] = False
                print("Files changed, syncing...")
                _run_sync(config)
    except KeyboardInterrupt:
        print("\nStopping watcher.")
        observer.stop()
    observer.join()
    _remove_pid(config.db_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="logseq-sync",
        description="Sync Logseq notes into the vector database.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Run incremental sync and exit")
    group.add_argument("--watch", action="store_true", help="Sync then watch for file changes")
    group.add_argument("--rebuild", action="store_true", help="Drop DB and re-index everything")
    group.add_argument("--status", action="store_true", help="Show staleness report")

    args = parser.parse_args()
    config = _load_config()

    if args.status:
        _show_status(config)
    elif args.rebuild:
        _run_sync(config, rebuild=True)
    elif args.watch:
        _watch(config)
    else:  # --once
        _run_sync(config)


if __name__ == "__main__":
    main()
