"""Search and DSL/datascript query tool handlers."""

import json

from mcp.types import Tool, TextContent

import mcp_logseq.tools as _t
from .. import access
from ..access import (
    is_page_excluded as _is_page_excluded,
    is_page_blocked as _is_page_blocked,
)
from ..namespace import is_namespace_blocked as _is_namespace_blocked
from .base import ToolHandler, logger, _UUID_REF_PATTERN


class SearchToolHandler(ToolHandler):
    # No pre-dispatch gate: results are filtered via a bespoke fail-closed
    # exclusion set (_build_excluded_page_names) inside _run.
    access_policy = []

    def __init__(self):
        super().__init__("search")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Search for content across LogSeq pages, blocks, and files",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 20,
                    },
                    "include_blocks": {
                        "type": "boolean",
                        "description": "Include block content results",
                        "default": True,
                    },
                    "include_pages": {
                        "type": "boolean",
                        "description": "Include page name results",
                        "default": True,
                    },
                    "include_files": {
                        "type": "boolean",
                        "description": "Include file name results",
                        "default": False,
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format (text or json). JSON includes block UUIDs and page identifiers for deep linking.",
                        "enum": ["text", "json"],
                        "default": "text",
                    },
                },
                "required": ["query"],
            },
        )

    @staticmethod
    def _build_excluded_page_names(
        api,
        exclude_tags: list[str],
        exclude_namespaces: list[str],
        include_namespaces: list[str],
    ) -> set[str]:
        """Return lowercased names of pages blocked by tag or namespace rules.

        Makes one extra api.list_pages() call when any rule is configured.
        Fail-closed: when rules are active but the page list cannot be built,
        the error propagates so the caller aborts rather than returning an empty
        (degraded) exclusion set that would let restricted content through.
        """
        if not exclude_tags and not exclude_namespaces and not include_namespaces:
            return set()
        try:
            pages = api.list_pages()
            blocked = set()
            for page in pages:
                name = page.get("originalName") or page.get("name", "")
                if not name:
                    continue
                if _is_page_excluded(page, exclude_tags) or _is_namespace_blocked(
                    name, include_namespaces, exclude_namespaces
                ):
                    blocked.add(name.lower())
            return blocked
        except Exception:
            # Rules are active here (guarded above), so we cannot determine what
            # to exclude. Fail-closed: re-raise so the search handler returns an
            # error instead of unfiltered results.
            logger.warning(
                "Could not build blocked page names while ACL rules are active; "
                "failing closed (search will error rather than leak)."
            )
            raise

    @staticmethod
    def _filter_db_block_results(
        block_results: list[dict],
        api,
        excluded_page_names: set[str],
    ) -> list[dict]:
        """Drop DB-mode content blocks whose owning page is excluded.

        DB-mode blocks carry a 'page' field = the owning page's UUID, so the
        owning page can be resolved to a name and checked against
        ``excluded_page_names`` (which already encodes BOTH tag and namespace
        exclusions). Fail-closed: when ``excluded_page_names`` is non-empty and a
        block's owning page cannot be resolved, the block is dropped.

        A non-empty ``excluded_page_names`` is authoritative: because
        ``_build_excluded_page_names`` fails closed when rules are active, an
        empty set genuinely means no active exclusions, so this is a no-op
        (no API calls) in that case.
        """
        if not excluded_page_names:
            return block_results

        page_uuids = [
            str(b.get("page")) for b in block_results if b.get("page")
        ]
        resolved = api.resolve_page_uuids(page_uuids) if page_uuids else {}

        kept: list[dict] = []
        for block in block_results:
            page_uuid = block.get("page")
            page_name = resolved.get(str(page_uuid)) if page_uuid else None
            if page_name is None:
                # Fail-closed: owning page unresolvable while a rule is active.
                continue
            if page_name.lower() in excluded_page_names:
                continue
            kept.append(block)
        return kept

    @staticmethod
    def _format_db_mode_results(
        result: dict, limit: int,
        include_blocks: bool, include_pages: bool, include_files: bool,
        excluded_page_names: set[str] = frozenset(),
        api=None,
    ) -> list[str]:
        """Format search results from DB-mode Logseq.

        DB-mode returns a flat 'blocks' array where each item has 'content',
        'uuid', 'page' (UUID), and 'page?' (bool). Pages and blocks are
        distinguished by the 'page?' flag.
        """
        parts: list[str] = []
        blocks = result.get("blocks", [])

        # Split into pages and content blocks
        page_results = [b for b in blocks if b.get("page?")]
        block_results = [b for b in blocks if not b.get("page?")]
        block_results = SearchToolHandler._filter_db_block_results(
            block_results, api, excluded_page_names
        )

        if include_pages and page_results:
            visible_pages = [
                p for p in page_results
                if (p.get("fullTitle") or p.get("title") or p.get("content", "")).lower()
                not in excluded_page_names
            ]
            if visible_pages:
                parts.append(f"## Matching Pages ({len(visible_pages)} found)")
                for page in visible_pages:
                    name = page.get("fullTitle") or page.get("title") or page.get("content", "")
                    parts.append(f"- {name}")
                parts.append("")

        if include_blocks and block_results:
            parts.append(f"## Content Blocks ({len(block_results)} found)")
            for i, block in enumerate(block_results[:limit]):
                content = block.get("content", "").strip()
                # Clean up full-text search highlight markers
                content = content.replace("$pfts_2lqh>$", "").replace("$<pfts_2lqh$", "")
                if content:
                    page_id = block.get("page", "")
                    uuid = block.get("uuid", "")
                    if len(content) > 150:
                        content = content[:150] + "..."
                    parts.append(f"{i + 1}. {content}")
                    parts.append(f"   uuid: {uuid}  page: {page_id}")
            parts.append("")

        if include_files and result.get("files"):
            parts.append(f"## Matching Files ({len(result['files'])} found)")
            for f in result["files"]:
                parts.append(f"- {f}")
            parts.append("")

        if result.get("hasMore?"):
            parts.append("*More results available — increase limit to see more*")

        total = len(blocks) + len(result.get("files", []))
        parts.append(f"\n**Total results found: {total}**")
        return parts

    @staticmethod
    def _format_markdown_mode_results(
        result: dict, limit: int,
        include_blocks: bool, include_pages: bool, include_files: bool,
        excluded_page_names: set[str] = frozenset(),
    ) -> list[str]:
        """Format search results from markdown-mode Logseq.

        Markdown-mode returns separate 'blocks' (with 'block/content'),
        'pages' (list of strings), 'pages-content' (with 'block/snippet'),
        and 'files' arrays.
        """
        parts: list[str] = []

        if include_blocks and result.get("blocks") and not excluded_page_names:
            # Only show blocks when no exclusion is active — markdown-mode blocks
            # carry block/content but no page identifier, so we cannot verify they
            # are safe to show (same rule as the page-snippets section below)
            blocks = result["blocks"]
            parts.append(f"## Content Blocks ({len(blocks)} found)")
            for i, block in enumerate(blocks[:limit]):
                content = block.get("block/content", "").strip()
                if content:
                    if len(content) > 150:
                        content = content[:150] + "..."
                    parts.append(f"{i + 1}. {content}")
            parts.append("")

        if include_pages and result.get("pages-content"):
            snippets = result["pages-content"]
            if not excluded_page_names:
                # Only show snippets when no exclusion is active — snippets carry no
                # page identifier so we cannot verify they are safe to show
                parts.append(f"## Page Snippets ({len(snippets)} found)")
                for i, snippet in enumerate(snippets[:limit]):
                    snippet_text = snippet.get("block/snippet", "").strip()
                    if snippet_text:
                        snippet_text = snippet_text.replace("$pfts_2lqh>$", "").replace(
                            "$<pfts_2lqh$", ""
                        )
                        if len(snippet_text) > 200:
                            snippet_text = snippet_text[:200] + "..."
                        parts.append(f"{i + 1}. {snippet_text}")
                parts.append("")

        if include_pages and result.get("pages"):
            pages = result["pages"]
            visible_pages = [p for p in pages if p.lower() not in excluded_page_names]
            if visible_pages:
                parts.append(f"## Matching Pages ({len(visible_pages)} found)")
                for page in visible_pages:
                    parts.append(f"- {page}")
                parts.append("")

        if include_files and result.get("files"):
            files = result["files"]
            parts.append(f"## Matching Files ({len(files)} found)")
            for f in files:
                parts.append(f"- {f}")
            parts.append("")

        if result.get("has-more?"):
            parts.append("*More results available — increase limit to see more*")

        total = (
            len(result.get("blocks", []))
            + len(result.get("pages", []))
            + len(result.get("pages-content", []))
            + len(result.get("files", []))
        )
        parts.append(f"\n**Total results found: {total}**")
        return parts

    @staticmethod
    def _build_json_results(
        result: dict, query: str, limit: int,
        include_blocks: bool, include_pages: bool, include_files: bool,
        excluded_page_names: set[str] = frozenset(),
        api=None,
    ) -> dict:
        """Build structured search results with UUIDs and page identifiers.

        Applies the same exclusion filtering, include flags, and limit as the
        text formatters, but preserves the raw fields (uuid, page) so callers
        can build logseq:// deep links without follow-up calls.
        """
        out: dict = {"query": query, "mode": "db" if _t._get_db_mode() else "markdown"}

        if _t._get_db_mode():
            blocks = result.get("blocks", [])
            if include_pages:
                out["pages"] = [
                    p for p in blocks
                    if p.get("page?")
                    and (p.get("fullTitle") or p.get("title") or p.get("content", "")).lower()
                    not in excluded_page_names
                ]
            if include_blocks:
                visible_blocks = SearchToolHandler._filter_db_block_results(
                    [b for b in blocks if not b.get("page?")],
                    api, excluded_page_names,
                )
                block_results = []
                for block in visible_blocks[:limit]:
                    block = dict(block)
                    content = block.get("content", "")
                    block["content"] = content.replace("$pfts_2lqh>$", "").replace(
                        "$<pfts_2lqh$", ""
                    )
                    block_results.append(block)
                out["blocks"] = block_results
            if include_files:
                out["files"] = result.get("files", [])
            out["has_more"] = bool(result.get("hasMore?"))
        else:
            if include_blocks and not excluded_page_names:
                # Markdown-mode blocks carry block/content but no page
                # identifier, so they cannot be exclusion-filtered — only expose
                # them when no exclusion is active (same rule as snippets)
                out["blocks"] = result.get("blocks", [])[:limit]
            if include_pages:
                out["pages"] = [
                    p for p in result.get("pages", [])
                    if p.lower() not in excluded_page_names
                ]
                if not excluded_page_names:
                    # Snippets carry no page identifier, so they cannot be
                    # exclusion-filtered — only expose them when no exclusion
                    # is active (same rule as text mode)
                    out["pages_content"] = result.get("pages-content", [])[:limit]
            if include_files:
                out["files"] = result.get("files", [])
            out["has_more"] = bool(result.get("has-more?"))

        return out

    def _run(self, api, args: dict) -> list[TextContent]:
        """Execute search and format results."""
        logger.info(f"Searching with args: {args}")

        if "query" not in args:
            raise RuntimeError("query argument required")

        query = args["query"]
        limit = args.get("limit", 20)
        include_blocks = args.get("include_blocks", True)
        include_pages = args.get("include_pages", True)
        include_files = args.get("include_files", False)

        try:
            # Prepare search options
            search_options = {"limit": limit}

            result = api.search_content(query, search_options)

            if not result:
                return [
                    TextContent(
                        type="text", text=f"No search results found for '{query}'"
                    )
                ]

            # Build excluded page name set (one extra API call only when needed)
            acl = access.get_access_config()
            excluded_page_names = self._build_excluded_page_names(
                api, acl.exclude_tags, acl.exclude_namespaces, acl.include_namespaces
            )

            if args.get("format") == "json":
                json_result = self._build_json_results(
                    result, query, limit, include_blocks, include_pages, include_files, excluded_page_names, api
                )
                return [TextContent(type="text", text=json.dumps(json_result, indent=2))]

            # Format results
            content_parts = []
            content_parts.append(f"# Search Results for '{query}'\n")

            if _t._get_db_mode():
                content_parts.extend(
                    self._format_db_mode_results(result, limit, include_blocks, include_pages, include_files, excluded_page_names, api)
                )
            else:
                content_parts.extend(
                    self._format_markdown_mode_results(result, limit, include_blocks, include_pages, include_files, excluded_page_names)
                )

            response_text = "\n".join(content_parts)

            return [TextContent(type="text", text=response_text)]

        except Exception as e:
            logger.error(f"Failed to search: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Search failed: {str(e)}"
            )]


class QueryToolHandler(ToolHandler):
    """Execute Logseq DSL queries to search pages and blocks."""

    # No pre-dispatch gate: page and block results are filtered via a bespoke
    # fail-closed tag/namespace check (_block_blocked / _is_page_blocked) in _run.
    access_policy = []

    def __init__(self):
        super().__init__("query")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Execute a Logseq DSL query to search pages and blocks. Supports property queries, tag queries, task queries, and logical combinations. See https://docs.logseq.com/#/page/queries for query syntax.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Logseq DSL query string (e.g., '(page-property status active)', '(and (task todo) (page [[Project]]))')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 100
                    },
                    "result_type": {
                        "type": "string",
                        "description": "Filter results by type",
                        "enum": ["all", "pages_only", "blocks_only"],
                        "default": "all"
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format (text or json). JSON returns raw result objects including block UUIDs and page info for deep linking.",
                        "enum": ["text", "json"],
                        "default": "text"
                    }
                },
                "required": ["query"]
            }
        )

    def _is_page(self, item: dict) -> bool:
        """Detect if a result item is a page based on available fields."""
        if not isinstance(item, dict):
            return False
        # Pages typically have originalName or name without block-specific fields
        has_page_fields = bool(item.get("originalName") or item.get("name"))
        has_block_content = bool(item.get("content") or item.get("block/content"))
        return has_page_fields and not has_block_content

    def _is_block(self, item: dict) -> bool:
        """Detect if a result item is a block based on available fields."""
        if not isinstance(item, dict):
            return False
        return bool(item.get("content") or item.get("block/content"))

    @staticmethod
    def _block_page_name(item: dict, api) -> str | None:
        """Resolve the owning page name for a DSL block result.

        Prefers the inline 'page' reference carried by the query result; falls
        back to an API lookup by block UUID. Returns None when it cannot be
        determined (callers treat that as fail-closed when rules are set).
        """
        page_ref = item.get("page")
        if isinstance(page_ref, dict):
            name = page_ref.get("originalName") or page_ref.get("name")
            if name:
                return name
        elif isinstance(page_ref, str) and page_ref:
            # A bare UUID string is NOT a trustworthy page name: under an
            # exclude-only policy a UUID matches no rule and would fail OPEN.
            # Resolve the page UUID to its real name so it's fail-closed.
            if _UUID_REF_PATTERN.fullmatch(f"[[{page_ref}]]"):
                return api.resolve_page_uuids([page_ref]).get(page_ref)
            return page_ref
        uuid = item.get("uuid")
        if uuid:
            return api.get_block_page_name(uuid)
        return None

    def _block_blocked(self, item: dict, api, cache: dict | None = None) -> bool:
        """Fail-closed tag AND namespace check for a DSL block result.

        Consulted whenever ANY rule (tag or namespace) is configured. The owning
        page is resolved once via ``_block_page_name``; the block is dropped if
        that page is namespace-blocked OR tag-excluded. A block whose owning page
        cannot be resolved is treated as blocked (fail-closed).

        ``cache`` is an optional per-request memo (page name -> blocked bool) so
        that many blocks sharing an owning page incur the tag fetch only once.
        """
        page_name = self._block_page_name(item, api)
        if page_name is None:
            return True
        if cache is not None and page_name in cache:
            return cache[page_name]

        blocked = self._page_name_blocked(page_name, api)
        if cache is not None:
            cache[page_name] = blocked
        return blocked

    def _page_name_blocked(self, page_name: str, api) -> bool:
        """Tag OR namespace block decision for an already-resolved page name."""
        acl = access.get_access_config()
        if _is_namespace_blocked(page_name, acl.include_namespaces, acl.exclude_namespaces):
            return True
        if acl.exclude_tags:
            # Tag exclusion needs the page's properties; fetch the owning page
            # and inspect its tags. Fail-closed if it cannot be fetched.
            try:
                page = api.get_page_content(page_name)
            except Exception:
                return True
            if page and _is_page_excluded(page.get("page", {}), acl.exclude_tags):
                return True
        return False

    def _format_item(self, item: dict, index: int) -> str:
        """Format a single result item with type indicator."""
        if not isinstance(item, dict):
            return f"{index}. {item}"

        if self._is_page(item):
            name = item.get("originalName") or item.get("name", "<unknown>")
            # Get properties if available
            props = item.get("propertiesTextValues", {}) or item.get("properties", {})
            props_str = ", ".join(f"{k}: {v}" for k, v in props.items()) if props else ""
            if props_str:
                return f"{index}. 📄 **{name}** ({props_str})"
            return f"{index}. 📄 **{name}**"
        elif self._is_block(item):
            content = item.get("content") or item.get("block/content", "")
            # Truncate long content
            if len(content) > 100:
                content = content[:100] + "..."
            return f"{index}. 📝 {content}"
        else:
            # Unknown type - just show what we have
            name = item.get("originalName") or item.get("name") or str(item)[:50]
            return f"{index}. {name}"

    def _run(self, api, args: dict) -> list[TextContent]:
        """Execute DSL query and format results."""
        if "query" not in args:
            raise RuntimeError("query argument required")

        query = args["query"]
        limit = args.get("limit", 100)
        result_type = args.get("result_type", "all")

        try:
            result = api.query_dsl(query)

            if not result:
                return [TextContent(
                    type="text",
                    text=f"No results found for query: `{query}`"
                )]

            # Filter by result_type if specified
            filtered_results = []
            for item in result:
                if result_type == "pages_only" and not self._is_page(item):
                    continue
                if result_type == "blocks_only" and not self._is_block(item):
                    continue
                filtered_results.append(item)

            # Security: filter page objects blocked by tag OR namespace, AND
            # block objects whose owning page is blocked by tag OR namespace.
            # A block's owning page is resolvable (_block_page_name), so its TAGS
            # are checkable too — block filtering must run whenever ANY rule is
            # active (tag-only profiles included). Resolution is fail-closed
            # (unresolvable owning page => dropped).
            if access.get_access_config().has_rules:
                filtered = []
                # Per-request memo so blocks sharing an owning page only trigger
                # one tag/namespace resolution + fetch.
                block_decision_cache: dict[str, bool] = {}
                for item in filtered_results:
                    if self._is_page(item):
                        name = item.get("originalName") or item.get("name", "")
                        if _is_page_blocked(item, name):
                            continue
                    elif self._is_block(item):
                        if self._block_blocked(item, api, block_decision_cache):
                            continue
                    filtered.append(item)
                filtered_results = filtered

            if not filtered_results:
                filter_msg = f" (filtered to {result_type})" if result_type != "all" else ""
                return [TextContent(
                    type="text",
                    text=f"No results found for query: `{query}`{filter_msg}"
                )]

            # Apply limit
            limited_results = filtered_results[:limit]

            if args.get("format") == "json":
                json_result = {
                    "query": query,
                    "total": len(filtered_results),
                    "results": limited_results,
                }
                return [TextContent(type="text", text=json.dumps(json_result, indent=2))]

            # Format results
            content_parts = []
            content_parts.append(f"# Query Results\n")
            content_parts.append(f"**Query:** `{query}`\n")

            for i, item in enumerate(limited_results, 1):
                content_parts.append(self._format_item(item, i))

            # Summary
            content_parts.append(f"\n---")
            if len(filtered_results) > limit:
                content_parts.append(f"**Showing {limit} of {len(filtered_results)} results** (increase limit to see more)")
            else:
                content_parts.append(f"**Total: {len(limited_results)} results**")

            return [TextContent(type="text", text="\n".join(content_parts))]

        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Query failed: {str(e)}\n\nMake sure the query syntax is valid. See https://docs.logseq.com/#/page/queries"
            )]
