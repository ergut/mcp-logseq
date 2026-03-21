"""
MCP tool handlers for vector search.

Registered conditionally in server.py only when vector.enabled is true.
Follows the same ToolHandler pattern as tools.py.
"""

from __future__ import annotations

import logging
import threading

from mcp.types import TextContent, Tool

from mcp_logseq.config import VectorConfig
from mcp_logseq.tools import ToolHandler
from mcp_logseq.vector.db import VectorDB
from mcp_logseq.vector.embedder import create_embedder
from mcp_logseq.vector.state import StateManager
from mcp_logseq.vector.sync import SyncEngine, check_staleness, _migrate_to_relative_keys
from mcp_logseq.vector.types import SearchParams, SyncResult

logger = logging.getLogger("mcp-logseq.vector.index")


class BackgroundSyncer:
    """Runs at most one sync at a time in a daemon thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_result: SyncResult | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    def trigger(self, config: VectorConfig) -> bool:
        """Start background sync. Returns True if started, False if already running."""
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return False
        thread = threading.Thread(target=self._run, args=(config,), daemon=True)
        thread.start()
        return True

    def _run(self, config: VectorConfig) -> None:
        db = None
        try:
            embedder = create_embedder(config.embedder)
            db = VectorDB.open(config.db_path, embedder.dimensions)
            state_mgr = StateManager(config.db_path)
            engine = SyncEngine(config, db, state_mgr, embedder)
            self._last_result = engine.sync()
            self._last_error = None
            logger.info(
                f"Background sync complete: +{self._last_result.added} "
                f"~{self._last_result.updated} -{self._last_result.deleted}"
            )
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Background sync failed: {e}", exc_info=True)
        finally:
            if db is not None:
                db.close()
            self._lock.release()


# Module-level singleton — shared across all tool handler instances in this process
_syncer = BackgroundSyncer()


_WEAK_MATCH_THRESHOLD = 0.80  # scores above this are likely tangential; AI should use judgment


def _relevance_label(score: float) -> str:
    if score < 0.65:
        return "high relevance"
    if score < _WEAK_MATCH_THRESHOLD:
        return "medium relevance"
    return "weak match"


def _format_search_results(results) -> str:
    if not results:
        return "No results found."
    lines = []
    has_weak = False
    for i, r in enumerate(results, 1):
        label = _relevance_label(r.score)
        if label == "weak match":
            has_weak = True
        lines.append(f"{i}. **{r.page}** (score: {r.score:.3f} — {label})")
        lines.append(f"   {r.text[:300]}{'...' if len(r.text) > 300 else ''}")
        meta_parts = []
        if r.tags:
            meta_parts.append(f"Tags: {', '.join(r.tags)}")
        if r.date:
            meta_parts.append(f"Date: {r.date}")
        if meta_parts:
            lines.append(f"   {' | '.join(meta_parts)}")
        lines.append("   ---")
    lines.append(
        "\nNote: score is a distance metric — lower is more relevant. "
        + ("Weak match results may not address the query; use judgment when presenting them." if has_weak
           else "All results are within the expected relevance range.")
    )
    return "\n".join(lines)


class VectorSearchToolHandler(ToolHandler):
    def __init__(self, config: VectorConfig) -> None:
        super().__init__("vector_search")
        self._config = config

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Semantic search over Logseq notes using hybrid search (vector similarity + "
                "full-text, combined by default). Use this for natural language queries about "
                "topics, concepts, or meaning — not for exact title lookups. "
                "Results include a relevance label and score (lower score = more relevant). "
                "Weak match results (score > 0.80) may be tangential; use judgment when "
                "presenting them to the user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only return results from pages that have ALL of these tags",
                    },
                    "filter_page": {
                        "type": "string",
                        "description": "Restrict search to a single page by title",
                    },
                    "search_mode": {
                        "type": "string",
                        "enum": ["hybrid", "vector", "keyword"],
                        "description": "Search mode: hybrid (default), vector-only, or keyword-only",
                        "default": "hybrid",
                    },
                },
                "required": ["query"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        query = args.get("query", "").strip()
        if not query:
            raise RuntimeError("query is required")

        top_k = min(int(args.get("top_k", 5)), 20)
        filter_tags = args.get("filter_tags")
        filter_page = args.get("filter_page")
        search_mode = args.get("search_mode", "hybrid")

        try:
            state_mgr = StateManager(self._config.db_path)
            state, meta = state_mgr.load()
            # Migrate legacy absolute-path keys (e.g. state written by container with different mount)
            state, migrated = _migrate_to_relative_keys(state, self._config.graph_path)
            if migrated:
                state_mgr.save(state, meta)
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading vector DB state: {e}")]

        if not meta.embedder_key:
            return [TextContent(
                type="text",
                text="Vector DB not initialized. Run sync_vector_db first.",
            )]

        # Staleness check — trigger background sync if stale
        output_prefix = ""
        try:
            report = check_staleness(self._config.graph_path, state)
            if report.stale:
                parts = []
                if report.changed_count:
                    parts.append(f"{report.changed_count} pages changed")
                if report.deleted_count:
                    parts.append(f"{report.deleted_count} pages deleted")
                detail = ", ".join(parts)
                if _syncer.trigger(self._config):
                    output_prefix = (
                        f"Note: {detail} since last sync — background sync started. "
                        f"Results below reflect the current DB state.\n\n"
                    )
                else:
                    output_prefix = (
                        f"Note: {detail} since last sync — sync already in progress.\n\n"
                    )
        except Exception as e:
            logger.warning(f"Staleness check failed: {e}")

        try:
            embedder = create_embedder(self._config.embedder)
            query_vector = embedder.embed([query])[0]
        except RuntimeError as e:
            return [TextContent(type="text", text=str(e))]
        except Exception as e:
            return [TextContent(type="text", text=f"Embedding failed: {e}")]

        try:
            db = VectorDB.open(self._config.db_path, meta.dimensions)
        except Exception as e:
            return [TextContent(type="text", text=f"Cannot open vector DB: {e}")]

        params = SearchParams(
            query_text=query,
            query_vector=query_vector,
            top_k=top_k,
            filter_tags=filter_tags,
            filter_page=filter_page,
            mode=search_mode,
        )

        try:
            results = db.search(params)
        except Exception as e:
            return [TextContent(type="text", text=f"Search failed: {e}")]
        finally:
            db.close()

        output = output_prefix + _format_search_results(results)
        return [TextContent(type="text", text=output)]


class SyncVectorDBToolHandler(ToolHandler):
    def __init__(self, config: VectorConfig) -> None:
        super().__init__("sync_vector_db")
        self._config = config

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Run incremental sync of the vector database against current Logseq graph files. "
                "Only changed files are re-embedded. Use rebuild=true to drop and re-index everything."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "rebuild": {
                        "type": "boolean",
                        "description": "If true, drop the entire DB and re-index from scratch",
                        "default": False,
                    },
                },
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        rebuild = bool(args.get("rebuild", False))

        try:
            embedder = create_embedder(self._config.embedder)
            # Probe dimensions before opening DB (may raise if Ollama is down)
            dimensions = embedder.dimensions
        except RuntimeError as e:
            return [TextContent(type="text", text=str(e))]
        except Exception as e:
            return [TextContent(type="text", text=f"Embedder error: {e}")]

        try:
            db = VectorDB.open(self._config.db_path, dimensions)
            state_mgr = StateManager(self._config.db_path)
            engine = SyncEngine(self._config, db, state_mgr, embedder)
            result = engine.sync(rebuild=rebuild)
        except RuntimeError as e:
            return [TextContent(type="text", text=str(e))]
        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Sync failed: {e}")]
        finally:
            try:
                db.close()
            except Exception:
                pass

        lines = [
            f"Sync complete in {result.duration_ms}ms",
            f"  Added:   {result.added} pages",
            f"  Updated: {result.updated} pages",
            f"  Deleted: {result.deleted} pages",
            f"  Skipped: {result.skipped} pages (unchanged)",
        ]
        return [TextContent(type="text", text="\n".join(lines))]


class VectorDBStatusToolHandler(ToolHandler):
    def __init__(self, config: VectorConfig) -> None:
        super().__init__("vector_db_status")
        self._config = config

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Show current state of the vector database without syncing.",
            inputSchema={"type": "object", "properties": {}},
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        try:
            state_mgr = StateManager(self._config.db_path)
            state, meta = state_mgr.load()
            # Migrate legacy absolute-path keys (e.g. state written by container with different mount)
            state, migrated = _migrate_to_relative_keys(state, self._config.graph_path)
            if migrated:
                state_mgr.save(state, meta)
        except Exception as e:
            return [TextContent(type="text", text=f"Error reading DB state: {e}")]

        if not meta.embedder_key:
            return [TextContent(
                type="text",
                text="Vector DB not initialized. Run sync_vector_db first.",
            )]

        try:
            db = VectorDB.open(self._config.db_path, meta.dimensions)
            stats = db.get_stats()
            db.close()
        except Exception as e:
            stats = {"total_chunks": "?", "total_pages": "?"}

        try:
            report = check_staleness(self._config.graph_path, state)
            staleness = "Up to date" if not report.stale else (
                f"Out of date ({report.changed_count} changed, {report.deleted_count} deleted)"
            )
        except Exception:
            staleness = "Unknown"

        lines = [
            f"Vector DB Status",
            f"  Embedder:    {meta.embedder_key}",
            f"  Dimensions:  {meta.dimensions}",
            f"  Total chunks: {stats['total_chunks']}",
            f"  Total pages:  {stats['total_pages']}",
            f"  Last sync:   {meta.last_full_sync or 'never'}",
            f"  Staleness:   {staleness}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]
