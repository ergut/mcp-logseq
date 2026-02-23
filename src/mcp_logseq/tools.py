import os
import logging
from typing import Any
from . import logseq
from . import parser
from mcp.types import Tool, TextContent

logger = logging.getLogger("mcp-logseq")

api_key = os.getenv("LOGSEQ_API_TOKEN", "")
if api_key == "":
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")
else:
    logger.info("Found LOGSEQ_API_TOKEN in environment")
    logger.debug(f"API Token starts with: {api_key[:5]}...")


class ToolHandler:
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> list[TextContent]:
        raise NotImplementedError()


# =============================================================================
# TOOL HANDLERS (with proper markdown parsing and block hierarchy)
# =============================================================================


class CreatePageToolHandler(ToolHandler):
    """
    Create a new page with proper block hierarchy.

    Parses markdown content into Logseq blocks, supporting:
    - Headings (# ## ###) with nested hierarchy
    - Bullet and numbered lists with nesting
    - Code blocks (fenced with ```)
    - Blockquotes (>)
    - YAML frontmatter for page properties
    """

    def __init__(self):
        super().__init__("create_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Create a new page in Logseq with properly structured blocks.

Markdown content is automatically parsed into Logseq's block hierarchy:
- Headings (# ## ###) create nested sections
- Lists (- or 1.) become proper block trees  
- Code blocks are preserved as single blocks
- YAML frontmatter (---) becomes page properties

Example content:
```
---
tags: [project, active]
priority: high
---

# Project Title
Introduction paragraph.

## Tasks
- Task 1
  - Subtask A
- Task 2
```""",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the new page"},
                    "content": {
                        "type": "string",
                        "description": "Markdown content to parse into blocks (optional)",
                    },
                    "properties": {
                        "type": "object",
                        "description": "Page properties (merged with frontmatter if both provided)",
                        "additionalProperties": True,
                    },
                },
                "required": ["title"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "title" not in args:
            raise RuntimeError("title argument required")

        title = args["title"]
        content = args.get("content", "")
        explicit_properties = args.get("properties", {})

        try:
            api = logseq.LogSeq(api_key=api_key)

            # Parse the content
            parsed = (
                parser.parse_content(content) if content else parser.ParsedContent()
            )

            # Merge properties: explicit properties override frontmatter
            page_properties = {**parsed.properties, **explicit_properties}

            # Convert blocks to batch format
            blocks = parsed.to_batch_format()

            # Create the page with blocks
            api.create_page_with_blocks(title, blocks, page_properties)

            # Build success message
            block_count = len(blocks)
            prop_count = len(page_properties)

            msg_parts = [f"Successfully created page '{title}'"]
            if block_count > 0:
                msg_parts.append(f"  - {block_count} top-level block(s) created")
            if prop_count > 0:
                msg_parts.append(f"  - {prop_count} page property/ies set")

            return [TextContent(type="text", text="\n".join(msg_parts))]
        except Exception as e:
            logger.error(f"Failed to create page: {str(e)}")
            raise


class ListPagesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("list_pages")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all pages in a LogSeq graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_journals": {
                        "type": "boolean",
                        "description": "Whether to include journal/daily notes in the list",
                        "default": False,
                    }
                },
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        include_journals = args.get("include_journals", False)

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.list_pages()

            # Format pages for display
            pages_info = []
            for page in result:
                # Skip if it's a journal page and we don't want to include those
                is_journal = page.get("journal?", False)
                if is_journal and not include_journals:
                    continue

                # Get page information
                name = page.get("originalName") or page.get("name", "<unknown>")

                # Build page info string
                info_parts = [f"- {name}"]
                if is_journal:
                    info_parts.append("[journal]")

                pages_info.append(" ".join(info_parts))

            # Sort alphabetically by page name
            pages_info.sort()

            # Build response
            count_msg = f"\nTotal pages: {len(pages_info)}"
            journal_msg = (
                " (excluding journal pages)"
                if not include_journals
                else " (including journal pages)"
            )

            response = (
                "LogSeq Pages:\n\n" + "\n".join(pages_info) + count_msg + journal_msg
            )

            return [TextContent(type="text", text=response)]

        except Exception as e:
            logger.error(f"Failed to list pages: {str(e)}")
            raise


class GetPageContentToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("get_page_content")

    @staticmethod
    def _format_block_tree(
        block: dict, indent_level: int = 0, max_depth: int = -1
    ) -> list[str]:
        """
        Recursively format a block and its children with proper indentation.

        Args:
            block: Block dict with 'content', 'children', and optional 'properties', 'marker'
            indent_level: Current indentation level (0-based)
            max_depth: Maximum depth to recurse (-1 for unlimited)

        Returns:
            List of formatted lines for this block and its children
        """
        lines = []

        # Get block content
        content = block.get("content", "").strip()
        if not content:
            return lines

        # Build the formatted line with indentation
        # Note: Properties are already included in the content by Logseq,
        # so we don't need to add them separately from block.properties
        indent = "  " * indent_level
        line = f"{indent}- {content}"
        lines.append(line)

        # Process children if we haven't hit the depth limit
        children = block.get("children", [])
        if children and (max_depth == -1 or indent_level < max_depth):
            for child in children:
                child_lines = GetPageContentToolHandler._format_block_tree(
                    child, indent_level + 1, max_depth
                )
                lines.extend(child_lines)

        return lines

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get the content of a specific page from LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to retrieve",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format (text or json)",
                        "enum": ["text", "json"],
                        "default": "text",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum nesting depth to display (default: -1 for unlimited)",
                        "default": -1,
                    },
                },
                "required": ["page_name"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        """Get and format LogSeq page content."""
        logger.info(f"Getting page content with args: {args}")

        if "page_name" not in args:
            raise RuntimeError("page_name argument required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.get_page_content(args["page_name"])

            if not result:
                return [
                    TextContent(
                        type="text", text=f"Page '{args['page_name']}' not found."
                    )
                ]

            # Handle JSON format request
            if args.get("format") == "json":
                return [TextContent(type="text", text=str(result))]

            # Format as readable text
            content_parts = []

            # Get blocks from the result structure
            # Note: Page properties are already in the first block's content,
            # so we don't need to show them separately in YAML frontmatter
            blocks = result.get("blocks", [])

            # Blocks content - use recursive formatter
            max_depth = args.get("max_depth", -1)
            if blocks:
                for block in blocks:
                    if isinstance(block, dict):
                        block_lines = self._format_block_tree(block, 0, max_depth)
                        content_parts.extend(block_lines)
                    elif isinstance(block, str) and block.strip():
                        content_parts.append(f"- {block}")
            else:
                # Empty page - return single dash
                content_parts.append("-")

            return [TextContent(type="text", text="\n".join(content_parts))]

        except Exception as e:
            logger.error(f"Failed to get page content: {str(e)}")
            raise


class DeletePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("delete_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Delete a page from LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to delete",
                    }
                },
                "required": ["page_name"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.delete_page(args["page_name"])

            # Build detailed success message
            page_name = args["page_name"]
            success_msg = f"✅ Successfully deleted page '{page_name}'"

            # Add any additional info from the API result if available
            if result and isinstance(result, dict):
                if result.get("success"):
                    success_msg += (
                        f"\n📋 Status: {result.get('message', 'Deletion confirmed')}"
                    )

            success_msg += (
                f"\n🗑️  Page '{page_name}' has been permanently removed from LogSeq"
            )

            return [TextContent(type="text", text=success_msg)]
        except ValueError as e:
            # Handle validation errors (page not found) gracefully
            return [TextContent(type="text", text=f"❌ Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Failed to delete page: {str(e)}")
            return [
                TextContent(
                    type="text",
                    text=f"❌ Failed to delete page '{args['page_name']}': {str(e)}",
                )
            ]


class UpdatePageToolHandler(ToolHandler):
    """
    Update a page with proper block hierarchy support.

    Supports two modes:
    - append: Add new blocks after existing content (default)
    - replace: Clear existing content and add new blocks
    """

    def __init__(self):
        super().__init__("update_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Update a page in Logseq with new content and/or properties.

Supports two modes:
- append: Add new blocks after existing content (default)
- replace: Clear all existing blocks and add new content

Markdown is parsed into proper block hierarchy just like create_page.
YAML frontmatter in content will be merged with explicit properties.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to update",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content to add or replace with",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "default": "append",
                        "description": "append: add after existing content. replace: clear page and add new content.",
                    },
                    "properties": {
                        "type": "object",
                        "description": "Page properties to set/update",
                        "additionalProperties": True,
                    },
                },
                "required": ["page_name"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument required")

        page_name = args["page_name"]
        content = args.get("content", "")
        mode = args.get("mode", "append")
        explicit_properties = args.get("properties", {})

        # Validate that at least one update is provided
        if not content and not explicit_properties:
            return [
                TextContent(
                    type="text",
                    text="Error: Either 'content' or 'properties' must be provided for update",
                )
            ]

        try:
            api = logseq.LogSeq(api_key=api_key)

            # Parse the content
            parsed = (
                parser.parse_content(content) if content else parser.ParsedContent()
            )

            # Merge properties: explicit properties override frontmatter
            page_properties = (
                {**parsed.properties, **explicit_properties}
                if (parsed.properties or explicit_properties)
                else None
            )

            # Convert blocks to batch format
            blocks = parsed.to_batch_format()

            # Update the page
            result = api.update_page_with_blocks(
                page_name, blocks, page_properties, mode=mode
            )

            # Build success message
            updates = result.get("updates", [])
            msg_parts = [f"Successfully updated page '{page_name}'"]

            for update_type, update_value in updates:
                if update_type == "cleared":
                    msg_parts.append("  - Existing content cleared")
                elif update_type == "properties":
                    msg_parts.append(f"  - {len(update_value)} property/ies updated")
                elif update_type == "blocks_replaced":
                    msg_parts.append(f"  - {update_value} block(s) added")
                elif update_type == "blocks_appended":
                    msg_parts.append(f"  - {update_value} block(s) appended")

            msg_parts.append(f"Mode: {mode}")

            return [TextContent(type="text", text="\n".join(msg_parts))]
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Failed to update page: {str(e)}")
            return [
                TextContent(
                    type="text", text=f"Failed to update page '{page_name}': {str(e)}"
                )
            ]


class DeleteBlockToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("delete_block")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Delete a block from LogSeq by its UUID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_uuid": {
                        "type": "string",
                        "description": "UUID of the block to delete"
                    }
                },
                "required": ["block_uuid"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "block_uuid" not in args:
            raise RuntimeError("block_uuid argument required")

        block_uuid = args["block_uuid"]

        try:
            api = logseq.LogSeq(api_key=api_key)
            api.delete_block(block_uuid)

            return [TextContent(
                type="text",
                text=f"✅ Successfully deleted block '{block_uuid}'"
            )]
        except ValueError as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Failed to delete block: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to delete block '{block_uuid}': {str(e)}"
            )]

class SearchToolHandler(ToolHandler):
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
                },
                "required": ["query"],
            },
        )

    def run_tool(self, args: dict) -> list[TextContent]:
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

            api = logseq.LogSeq(api_key=api_key)
            result = api.search_content(query, search_options)

            if not result:
                return [
                    TextContent(
                        type="text", text=f"No search results found for '{query}'"
                    )
                ]

            # Format results
            content_parts = []
            content_parts.append(f"# Search Results for '{query}'\n")

            # Block results
            if include_blocks and result.get("blocks"):
                blocks = result["blocks"]
                content_parts.append(f"## 📄 Content Blocks ({len(blocks)} found)")
                for i, block in enumerate(blocks[:limit]):
                    # LogSeq returns blocks with 'block/content' key
                    content = block.get("block/content", "").strip()
                    if content:
                        # Truncate long content
                        if len(content) > 150:
                            content = content[:150] + "..."
                        content_parts.append(f"{i + 1}. {content}")
                content_parts.append("")

            # Page snippet results
            if include_blocks and result.get("pages-content"):
                snippets = result["pages-content"]
                content_parts.append(f"## 📝 Page Snippets ({len(snippets)} found)")
                for i, snippet in enumerate(snippets[:limit]):
                    # LogSeq returns snippets with 'block/snippet' key
                    snippet_text = snippet.get("block/snippet", "").strip()
                    if snippet_text:
                        # Clean up snippet text
                        snippet_text = snippet_text.replace("$pfts_2lqh>$", "").replace(
                            "$<pfts_2lqh$", ""
                        )
                        if len(snippet_text) > 200:
                            snippet_text = snippet_text[:200] + "..."
                        content_parts.append(f"{i + 1}. {snippet_text}")
                content_parts.append("")

            # Page name results
            if include_pages and result.get("pages"):
                pages = result["pages"]
                content_parts.append(f"## 📑 Matching Pages ({len(pages)} found)")
                for page in pages:
                    content_parts.append(f"- {page}")
                content_parts.append("")

            # File results
            if include_files and result.get("files"):
                files = result["files"]
                content_parts.append(f"## 📁 Matching Files ({len(files)} found)")
                for file_path in files:
                    content_parts.append(f"- {file_path}")
                content_parts.append("")

            # Pagination info
            if result.get("has-more?"):
                content_parts.append(
                    "📌 *More results available - increase limit to see more*"
                )

            # Summary
            total_results = (
                len(result.get("blocks", []))
                + len(result.get("pages", []))
                + len(result.get("files", []))
            )
            content_parts.append(f"\n**Total results found: {total_results}**")

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

    def run_tool(self, args: dict) -> list[TextContent]:
        """Execute DSL query and format results."""
        if "query" not in args:
            raise RuntimeError("query argument required")

        query = args["query"]
        limit = args.get("limit", 100)
        result_type = args.get("result_type", "all")

        try:
            api = logseq.LogSeq(api_key=api_key)
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

            if not filtered_results:
                filter_msg = f" (filtered to {result_type})" if result_type != "all" else ""
                return [TextContent(
                    type="text",
                    text=f"No results found for query: `{query}`{filter_msg}"
                )]

            # Apply limit
            limited_results = filtered_results[:limit]

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


class FindPagesByPropertyToolHandler(ToolHandler):
    """Find pages by property name and optional value."""

    def __init__(self):
        super().__init__("find_pages_by_property")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Find all pages that have a specific property, optionally filtered by value. Simpler alternative to the full query DSL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "property_name": {
                        "type": "string",
                        "description": "Name of the property to search for (e.g., 'status', 'type', 'service')"
                    },
                    "property_value": {
                        "type": "string",
                        "description": "Optional: specific value to match. If omitted, returns all pages that have this property."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 100
                    }
                },
                "required": ["property_name"]
            }
        )

    def _escape_value(self, value: str) -> str:
        """Escape special characters in property values for DSL query."""
        # Escape double quotes
        return value.replace('"', '\\"')

    def run_tool(self, args: dict) -> list[TextContent]:
        """Find pages by property and format results."""
        if "property_name" not in args:
            raise RuntimeError("property_name argument required")

        property_name = args["property_name"]
        property_value = args.get("property_value")
        limit = args.get("limit", 100)

        # Build the DSL query
        if property_value:
            escaped_value = self._escape_value(property_value)
            query = f'(page-property {property_name} "{escaped_value}")'
        else:
            query = f'(page-property {property_name})'

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.query_dsl(query)

            if not result:
                if property_value:
                    msg = f"No pages found with property '{property_name} = {property_value}'"
                else:
                    msg = f"No pages found with property '{property_name}'"
                return [TextContent(type="text", text=msg)]

            # Apply limit
            limited_results = result[:limit]

            # Format results
            content_parts = []

            if property_value:
                content_parts.append(f"# Pages with '{property_name} = {property_value}'\n")
            else:
                content_parts.append(f"# Pages with property '{property_name}'\n")

            for item in limited_results:
                if isinstance(item, dict):
                    name = item.get("originalName") or item.get("name", "<unknown>")
                    props = item.get("propertiesTextValues", {}) or item.get("properties", {})

                    # Show the property value if we searched without a specific value
                    if not property_value and property_name in props:
                        content_parts.append(f"- **{name}** ({property_name}: {props[property_name]})")
                    elif not property_value and property_name.lower() in props:
                        content_parts.append(f"- **{name}** ({property_name}: {props[property_name.lower()]})")
                    else:
                        content_parts.append(f"- **{name}**")
                else:
                    content_parts.append(f"- {item}")

            # Summary
            content_parts.append(f"\n---")
            if len(result) > limit:
                content_parts.append(f"**Showing {limit} of {len(result)} pages** (increase limit to see more)")
            else:
                content_parts.append(f"**Total: {len(limited_results)} pages**")

            return [TextContent(type="text", text="\n".join(content_parts))]

        except Exception as e:
            logger.error(f"Property search failed: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Search failed: {str(e)}"
            )]
class GetPagesFromNamespaceToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("get_pages_from_namespace")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get all pages within a namespace hierarchy (flat list). Use this to discover subpages of a parent page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "The namespace to query (e.g., 'Customer', 'Projects/2024')"
                    }
                },
                "required": ["namespace"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "namespace" not in args:
            raise RuntimeError("namespace argument required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.get_pages_from_namespace(args["namespace"])

            if not result:
                return [TextContent(
                    type="text",
                    text=f"No pages found in namespace '{args['namespace']}'"
                )]

            # Format pages for display
            pages_info = []
            for page in result:
                name = page.get('originalName') or page.get('name', '<unknown>')
                pages_info.append(f"- {name}")

            pages_info.sort()

            response = f"Pages in namespace '{args['namespace']}':\n\n"
            response += "\n".join(pages_info)
            response += f"\n\nTotal: {len(pages_info)} pages"

            return [TextContent(type="text", text=response)]

        except Exception as e:
            logger.error(f"Failed to get pages from namespace: {str(e)}")
            raise


class GetPagesTreeFromNamespaceToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("get_pages_tree_from_namespace")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get pages within a namespace as a hierarchical tree structure. Useful for understanding the full page hierarchy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "The root namespace to build tree from (e.g., 'Projects')"
                    }
                },
                "required": ["namespace"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "namespace" not in args:
            raise RuntimeError("namespace argument required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.get_pages_tree_from_namespace(args["namespace"])

            if not result:
                return [TextContent(
                    type="text",
                    text=f"No pages found in namespace '{args['namespace']}'"
                )]

            # Format as tree structure
            def format_tree(pages, prefix="", is_last_list=None):
                if is_last_list is None:
                    is_last_list = []
                lines = []
                for i, page in enumerate(pages):
                    is_last = i == len(pages) - 1
                    name = page.get('originalName') or page.get('name', '<unknown>')

                    # Build the prefix for this line
                    if prefix == "":
                        lines.append(name)
                    else:
                        connector = "└── " if is_last else "├── "
                        lines.append(f"{prefix}{connector}{name}")

                    # Handle children if present
                    children = page.get('children', [])
                    if children:
                        # Build prefix for children
                        if prefix == "":
                            child_prefix = ""
                        else:
                            child_prefix = prefix + ("    " if is_last else "│   ")
                        lines.extend(format_tree(children, child_prefix, is_last_list + [is_last]))
                return lines

            tree_lines = format_tree(result)

            response = f"Page tree for namespace '{args['namespace']}':\n\n"
            response += "\n".join(tree_lines)

            return [TextContent(type="text", text=response)]

        except Exception as e:
            logger.error(f"Failed to get pages tree: {str(e)}")
            raise


class RenamePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("rename_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Rename an existing page. All references throughout the graph will be automatically updated.",
            inputSchema={
                "type": "object",
                "properties": {
                    "old_name": {
                        "type": "string",
                        "description": "Current name of the page"
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New name for the page"
                    }
                },
                "required": ["old_name", "new_name"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "old_name" not in args or "new_name" not in args:
            raise RuntimeError("old_name and new_name arguments required")

        old_name = args["old_name"]
        new_name = args["new_name"]

        try:
            api = logseq.LogSeq(api_key=api_key)
            api.rename_page(old_name, new_name)

            return [TextContent(
                type="text",
                text=f"Successfully renamed page '{old_name}' to '{new_name}'\n"
                     f"All references in the graph have been updated."
            )]
        except ValueError as e:
            return [TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Failed to rename page: {str(e)}")
            return [TextContent(
                type="text",
                text=f"Failed to rename page: {str(e)}"
            )]


class GetPageBacklinksToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("get_page_backlinks")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get all pages and blocks that link to a specific page (backlinks/linked references).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to find backlinks for"
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include the content of referencing blocks",
                        "default": True
                    }
                },
                "required": ["page_name"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument required")

        page_name = args["page_name"]
        include_content = args.get("include_content", True)

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.get_page_linked_references(page_name)

            if not result:
                return [TextContent(
                    type="text",
                    text=f"No backlinks found for page '{page_name}'"
                )]

            # Format results
            # API returns: [[PageEntity, [BlockEntity, ...]], ...]
            content_parts = []
            content_parts.append(f"# Backlinks for '{page_name}'\n")

            total_refs = 0

            for item in result:
                if not isinstance(item, list) or len(item) < 2:
                    continue

                page_info, blocks = item[0], item[1]

                # Get page name
                ref_page_name = page_info.get('originalName') or page_info.get('name', '<unknown>')
                block_count = len(blocks) if blocks else 0
                total_refs += block_count

                content_parts.append(f"**{ref_page_name}** ({block_count} reference{'s' if block_count != 1 else ''})")

                # Include block content if requested
                if include_content and blocks:
                    for block in blocks:
                        block_content = block.get('content', '').strip()
                        if block_content:
                            # Truncate long content
                            if len(block_content) > 150:
                                block_content = block_content[:150] + "..."
                            content_parts.append(f"  - {block_content}")

                content_parts.append("")

            # Summary
            page_count = len(result)
            content_parts.append(f"---\n**Total: {page_count} page{'s' if page_count != 1 else ''}, {total_refs} reference{'s' if total_refs != 1 else ''}**")

            return [TextContent(type="text", text="\n".join(content_parts))]

        except Exception as e:
            logger.error(f"Failed to get backlinks: {str(e)}")
            return [TextContent(
                type="text",
                text=f"Failed to get backlinks: {str(e)}"
            )]
class InsertNestedBlockToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("insert_nested_block")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Insert a new block as a child or sibling of an existing block, enabling nested hierarchical structures""",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_block_uuid": {
                        "type": "string",
                        "description": "UUID of the reference block. If sibling=false, new block becomes a CHILD of this UUID. If sibling=true, new block becomes a SIBLING of this UUID (at the same level)."
                    },
                    "content": {
                        "type": "string",
                        "description": "Content text for the new block"
                    },
                    "properties": {
                        "type": "object",
                        "description": "Optional block properties (e.g., {'marker': 'TODO', 'priority': 'A'})",
                        "additionalProperties": True
                    },
                    "sibling": {
                        "type": "boolean",
                        "description": "false (default) = insert as CHILD under parent_block_uuid. true = insert as SIBLING after parent_block_uuid at the same level. For multiple children under same parent, ALWAYS use false with the parent's UUID.",
                        "default": False
                    }
                },
                "required": ["parent_block_uuid", "content"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        """Insert a nested block under an existing block."""
        if "parent_block_uuid" not in args or "content" not in args:
            raise RuntimeError("parent_block_uuid and content arguments required")

        parent_uuid = args["parent_block_uuid"]
        content = args["content"]
        properties = args.get("properties")
        sibling = args.get("sibling", False)

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.insert_block_as_child(
                parent_block_uuid=parent_uuid,
                content=content,
                properties=properties,
                sibling=sibling
            )

            relationship = "sibling" if sibling else "child"
            success_msg = f"✅ Successfully inserted block as {relationship}"

            # Add block details if available
            if result and isinstance(result, dict):
                if result.get("uuid"):
                    success_msg += f"\n🆔 New block UUID: {result.get('uuid')}"
                if result.get("content"):
                    content_preview = result.get('content')
                    if len(content_preview) > 100:
                        content_preview = content_preview[:100] + "..."
                    success_msg += f"\n📝 Content: {content_preview}"

            success_msg += f"\n🔗 Inserted under parent: {parent_uuid}"

            return [TextContent(
                type="text",
                text=success_msg
            )]

        except ValueError as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Failed to insert nested block: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to insert nested block: {str(e)}"
            )]
