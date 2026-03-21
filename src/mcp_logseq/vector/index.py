"""
MCP tool handlers for vector search.

Registered conditionally in server.py only when vector.enabled is true.
Follows the same ToolHandler pattern as tools.py.
"""

from __future__ import annotations

import logging

from mcp.types import TextContent, Tool

from mcp_logseq.config import VectorConfig
from mcp_logseq.tools import ToolHandler
from mcp_logseq.vector.db import VectorDB
from mcp_logseq.vector.embedder import create_embedder
from mcp_logseq.vector.state import StateManager
from mcp_logseq.vector.sync import SyncEngine, check_staleness
from mcp_logseq.vector.types import SearchParams

logger = logging.getLogger("mcp-logseq.vector.index")


def _format_staleness_warning(report) -> str | None:
    if not report.stale:
        return None
    parts = []
    if report.changed_count:
        parts.append(f"{report.changed_count} pages changed")
    if report.deleted_count:
        parts.append(f"{report.deleted_count} pages deleted")
    detail = ", ".join(parts)
    return (
        f"Warning: Vector DB may be out of date ({detail} since last sync). "
        f"Call sync_vector_db to update.\n\n"
    )


def _format_search_results(results) -> str:
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        score_str = f"{r.score:.3f}"
        lines.append(f"{i}. **{r.page}** (score: {score_str})")
        lines.append(f"   {r.text[:300]}{'...' if len(r.text) > 300 else ''}")
        meta_parts = []
        if r.tags:
            meta_parts.append(f"Tags: {', '.join(r.tags)}")
        if r.date:
            meta_parts.append(f"Date: {r.date}")
        if meta_parts:
            lines.append(f"   {' | '.join(meta_parts)}")
        lines.append("   ---")
    return "\n".join(lines)


class VectorSearchToolHandler(ToolHandler):
    def __init__(self, config: VectorConfig) -> None:
        super().__init__("vector_search")
        self._config = config

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Semantic search over Logseq notes using vector similarity and full-text search. "
                "Returns the most relevant note chunks for a natural language query."
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
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading vector DB state: {e}")]

        if not meta.embedder_key:
            return [TextContent(
                type="text",
                text="Vector DB not initialized. Run sync_vector_db first.",
            )]

        # Staleness check
        output_prefix = ""
        try:
            report = check_staleness(self._config.graph_path, state)
            warning = _format_staleness_warning(report)
            if warning:
                output_prefix = warning
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
