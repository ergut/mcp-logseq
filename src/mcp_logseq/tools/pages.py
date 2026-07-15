"""Page-level tool handlers (create, read, update, delete, rename, backlinks, property search)."""

import json
import re

from mcp.types import Tool, TextContent

import mcp_logseq.tools as _t
from .. import parser
from .. import access
from ..access import (
    AccessDenied,
    is_page_blocked as _is_page_blocked,
    enforce_namespace_access as _enforce_namespace_access,
    enforce_page_tag_access as _enforce_page_tag_access,
)
from .base import (
    ToolHandler,
    logger,
    _UUID_REF_PATTERN,
    _collect_block_uuids,
    _resolve_block_refs,
)


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

Fails if a page with the same title already exists (use update_page to modify
existing pages). This makes retries safe: re-sending a create_page that timed
out will not create numbered duplicates like "Page(1)".

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

        _enforce_namespace_access(title)

        try:
            api = _t._make_api()

            # Refuse to create a duplicate: Logseq auto-numbers pages with an
            # existing name ("Page(1)", "Page 2"), which silently fragments
            # content when a timed-out create_page is retried (issue #58).
            if api.page_exists(title):
                raise ValueError(
                    f"Page '{title}' already exists. Use update_page to modify "
                    "it (mode='append' or mode='replace'), or get_page_content "
                    "to inspect it. If a previous create_page call timed out, "
                    "the page may already contain the content you sent."
                )

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
            api = _t._make_api()
            result = api.list_pages()

            # Format pages for display
            pages_info = []
            for page in result:
                # Skip if it's a journal page and we don't want to include those
                is_journal = page.get("journal?", False)
                if is_journal and not include_journals:
                    continue
                # Security: pages blocked by tag OR namespace are invisible
                name_for_check = page.get("originalName") or page.get("name", "")
                if _is_page_blocked(page, name_for_check):
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
        block: dict, indent_level: int = 0, max_depth: int = -1,
        db_properties: dict[str, dict[str, str]] | None = None,
        uuid_map: dict[str, str] | None = None,
    ) -> list[str]:
        """
        Recursively format a block and its children with proper indentation.

        Args:
            block: Block dict with 'content', 'children', and optional 'properties', 'marker'
            indent_level: Current indentation level (0-based)
            max_depth: Maximum depth to recurse (-1 for unlimited)
            db_properties: DB-mode class properties keyed by block UUID
            uuid_map: Mapping of page UUIDs to page names for resolving [[uuid]] refs

        Returns:
            List of formatted lines for this block and its children
        """
        lines = []

        # Get block content
        content = block.get("content", "").strip()

        # Resolve [[uuid]] references to [[Page Name]] if a map is provided
        if uuid_map and content:
            content = _resolve_block_refs(content, uuid_map)
        if not content:
            return lines

        # Build the formatted line with indentation.
        # Skip adding "- " if the content already starts with it to avoid
        # double-wrapping blocks whose text begins with a list marker.
        indent = "  " * indent_level
        if content.startswith(("- ", "* ", "+ ")) or content in ("-", "*", "+"):
            line = f"{indent}{content}"
        else:
            line = f"{indent}- {content}"
        lines.append(line)

        # In DB-mode, properties are NOT embedded in content — render from dict
        # In Markdown-mode, properties are already in block content — skip to avoid duplicates
        if _t._get_db_mode():
            properties = block.get("properties", {})
            if properties:
                for key, value in properties.items():
                    if isinstance(key, str) and key.startswith(":logseq"):
                        continue
                    if f"{key}::" not in content:
                        lines.append(f"{indent}  {key}:: {value}")

            # DB-mode class properties (from datascript query)
            block_uuid = str(block.get("uuid", ""))
            if db_properties and block_uuid in db_properties:
                for key, value in db_properties[block_uuid].items():
                    lines.append(f"{indent}  {key}:: {value}")

        # Process children if we haven't hit the depth limit
        children = block.get("children", [])
        if children and (max_depth == -1 or indent_level < max_depth):
            for child in children:
                child_lines = GetPageContentToolHandler._format_block_tree(
                    child, indent_level + 1, max_depth, db_properties, uuid_map
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
                    "resolve_refs": {
                        "type": "boolean",
                        "description": "Resolve [[uuid]] page references to [[Page Name]] in DB mode (default: true)",
                        "default": True,
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

        # Pre-flight: namespace check is name-based, no API call needed
        _enforce_namespace_access(args["page_name"])

        try:
            api = _t._make_api()
            result = api.get_page_content(args["page_name"])

            if not result:
                return [
                    TextContent(
                        type="text", text=f"Page '{args['page_name']}' not found."
                    )
                ]

            # Security: block access to restricted pages (tag OR namespace) — fail loudly
            if _is_page_blocked(result.get("page", {}), args["page_name"]):
                raise AccessDenied(
                    f"Access denied: page '{args['page_name']}' is restricted "
                    f"and cannot be accessed by this assistant."
                )

            # Handle JSON format request
            if args.get("format") == "json":
                # In DB mode with resolve_refs, enrich JSON with resolved page names
                if _t._get_db_mode() and args.get("resolve_refs", True):
                    blocks = result.get("blocks", [])
                    page_uuids = _collect_block_uuids(blocks)
                    if page_uuids:
                        try:
                            uuid_map = api.resolve_page_uuids(list(page_uuids))
                            if uuid_map:
                                result = dict(result)
                                result["resolved_refs"] = uuid_map
                        except Exception as e:
                            logger.warning(f"Could not resolve refs for JSON: {e}")
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            # Format as readable text
            content_parts = []

            # Get blocks from the result structure
            blocks = result.get("blocks", [])

            # Fetch DB-mode class properties (only when LOGSEQ_DB_MODE is enabled)
            db_properties = {}
            uuid_map: dict[str, str] = {}
            if _t._get_db_mode():
                try:
                    db_properties = api.get_blocks_db_properties(blocks)
                    logger.info(f"DB-mode properties found for {len(db_properties)} blocks")
                except Exception as e:
                    logger.warning(f"Could not fetch DB-mode properties: {e}")

                # Resolve [[uuid]] page references to readable names
                resolve_refs = args.get("resolve_refs", True)
                if resolve_refs:
                    try:
                        page_uuids = _collect_block_uuids(blocks)
                        if page_uuids:
                            uuid_map = api.resolve_page_uuids(list(page_uuids))
                    except Exception as e:
                        logger.warning(f"Could not resolve page refs: {e}")

            # Blocks content - use recursive formatter
            max_depth = args.get("max_depth", -1)
            if blocks:
                for block in blocks:
                    if isinstance(block, dict):
                        block_lines = self._format_block_tree(
                            block, 0, max_depth, db_properties, uuid_map
                        )
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

        _enforce_namespace_access(args["page_name"])

        try:
            api = _t._make_api()
            _enforce_page_tag_access(api, args["page_name"])
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
        except AccessDenied:
            raise
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

        _enforce_namespace_access(page_name)

        # Validate that at least one update is provided
        if not content and not explicit_properties:
            return [
                TextContent(
                    type="text",
                    text="Error: Either 'content' or 'properties' must be provided for update",
                )
            ]

        try:
            api = _t._make_api()
            _enforce_page_tag_access(api, page_name)

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
        except AccessDenied:
            raise
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Failed to update page: {str(e)}")
            return [
                TextContent(
                    type="text", text=f"Failed to update page '{page_name}': {str(e)}"
                )
            ]


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
        return value.replace('"', '\\"')

    def _validate_property_name(self, name: str) -> str:
        """Validate and return property name, raising if it contains unsafe characters."""
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
            raise ValueError(f"Invalid property name '{name}': only alphanumeric, hyphens, and underscores allowed")
        return name

    def run_tool(self, args: dict) -> list[TextContent]:
        """Find pages by property and format results."""
        if "property_name" not in args:
            raise RuntimeError("property_name argument required")

        try:
            property_name = self._validate_property_name(args["property_name"])
        except ValueError as e:
            return [TextContent(type="text", text=f"❌ {str(e)}")]
        property_value = args.get("property_value")
        limit = args.get("limit", 100)

        # Build the DSL query
        if property_value:
            escaped_value = self._escape_value(property_value)
            query = f'(page-property {property_name} "{escaped_value}")'
        else:
            query = f'(page-property {property_name})'

        try:
            api = _t._make_api()
            result = api.query_dsl(query)

            if not result:
                if property_value:
                    msg = f"No pages found with property '{property_name} = {property_value}'"
                else:
                    msg = f"No pages found with property '{property_name}'"
                return [TextContent(type="text", text=msg)]

            # Security: drop pages blocked by tag OR namespace before limiting
            if access.get_access_config().has_rules:
                kept = []
                for item in result:
                    if isinstance(item, dict):
                        name = item.get("originalName") or item.get("name", "")
                        if _is_page_blocked(item, name):
                            continue
                    kept.append(item)
                result = kept

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

        _enforce_namespace_access(old_name)
        _enforce_namespace_access(new_name)

        try:
            api = _t._make_api()
            # Tag-on-write: guard the SOURCE page (existing). The target name is
            # a not-yet-existing page, so it has no prior tags to check.
            _enforce_page_tag_access(api, old_name)
            api.rename_page(old_name, new_name)

            return [TextContent(
                type="text",
                text=f"Successfully renamed page '{old_name}' to '{new_name}'\n"
                     f"All references in the graph have been updated."
            )]
        except AccessDenied:
            raise
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

        _enforce_namespace_access(page_name)

        try:
            api = _t._make_api()
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
            shown_pages = 0

            for item in result:
                if not isinstance(item, list) or len(item) < 2:
                    continue

                page_info, blocks = item[0], item[1]

                # Guard against None page entity (can occur in Logseq DB mode)
                if not isinstance(page_info, dict):
                    continue

                # Get page name
                ref_page_name = page_info.get('originalName') or page_info.get('name', '<unknown>')

                # Security: silently skip referencing pages blocked by namespace.
                # page_info rarely carries 'properties' so tag filtering falls back
                # to namespace-only; pass page_info anyway so tag check fires if
                # properties happen to be present.
                if _is_page_blocked(page_info, ref_page_name):
                    continue
                shown_pages += 1
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

            # Summary: count only referrers that survived filtering, so the
            # footer never reveals that hidden (blocked) referrers exist.
            page_count = shown_pages
            content_parts.append(f"---\n**Total: {page_count} page{'s' if page_count != 1 else ''}, {total_refs} reference{'s' if total_refs != 1 else ''}**")

            return [TextContent(type="text", text="\n".join(content_parts))]

        except Exception as e:
            logger.error(f"Failed to get backlinks: {str(e)}")
            return [TextContent(
                type="text",
                text=f"Failed to get backlinks: {str(e)}"
            )]
