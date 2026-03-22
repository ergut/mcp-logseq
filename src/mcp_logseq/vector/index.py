"""
MCP tool handlers for vector search.

Registered conditionally in server.py only when vector.enabled is true.
Follows the same ToolHandler pattern as tools.py.

Architecture: The MCP server is a read-only consumer of the vector DB.
All writes go through the logseq-sync CLI (single-writer principle).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from mcp.types import TextContent, Tool

from mcp_logseq.config import VectorConfig
from mcp_logseq.tools import ToolHandler
from mcp_logseq.vector.db import VectorDB
from mcp_logseq.vector.embedder import create_embedder
from mcp_logseq.vector.state import StateManager
from mcp_logseq.vector.sync import check_staleness
from mcp_logseq.vector.types import SearchParams

logger = logging.getLogger("mcp-logseq.vector.index")


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


def _check_watcher_running(db_path: str) -> str:
    """Check if logseq-sync --watch is running by reading its PID file."""
    pid_path = Path(db_path) / "sync.pid"
    if not pid_path.exists():
        return "not running"
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists
        return f"running (PID {pid})"
    except (ValueError, ProcessLookupError, PermissionError):
        return "not running"


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
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading vector DB state: {e}")]

        if not meta.embedder_key:
            return [TextContent(
                type="text",
                text="Vector DB not initialized. Run sync_vector_db first.",
            )]

        # Staleness check — informational only, no writes
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
                output_prefix = (
                    f"Note: {detail} since last sync. "
                    f"Ensure logseq-sync --watch is running, or call sync_vector_db. "
                    f"Results below may be incomplete.\n\n"
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
            db = VectorDB.open_readonly(self._config.db_path, meta.dimensions)
        except RuntimeError as e:
            return [TextContent(type="text", text=str(e))]
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

        cmd = [sys.executable, "-m", "mcp_logseq.bin.logseq_sync"]
        cmd.append("--rebuild" if rebuild else "--once")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            return [TextContent(type="text", text="Sync timed out after 10 minutes.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Sync failed: {e}")]

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return [TextContent(type="text", text=f"Sync failed:\n{error}")]

        return [TextContent(type="text", text=result.stdout.strip())]


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
            db = VectorDB.open_readonly(self._config.db_path, meta.dimensions)
            stats = db.get_stats()
            db.close()
        except RuntimeError as e:
            # open_readonly gives clear diagnostics (version mismatch, not initialized)
            return [TextContent(type="text", text=str(e))]
        except Exception:
            stats = {"total_chunks": "?", "total_pages": "?"}

        try:
            report = check_staleness(self._config.graph_path, state)
            staleness = "Up to date" if not report.stale else (
                f"Out of date ({report.changed_count} changed, {report.deleted_count} deleted)"
            )
        except Exception:
            staleness = "Unknown"

        watcher = _check_watcher_running(self._config.db_path)

        lines = [
            "Vector DB Status",
            f"  Embedder:     {meta.embedder_key}",
            f"  Dimensions:   {meta.dimensions}",
            f"  Total chunks: {stats['total_chunks']}",
            f"  Total pages:  {stats['total_pages']}",
            f"  Last sync:    {meta.last_full_sync or 'never'}",
            f"  Staleness:    {staleness}",
            f"  Watcher:      {watcher}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]
