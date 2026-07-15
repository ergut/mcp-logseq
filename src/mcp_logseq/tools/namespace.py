"""Namespace tree tool handlers."""

from mcp.types import Tool, TextContent

import mcp_logseq.tools as _t
from ..access import (
    is_page_blocked as _is_page_blocked,
    enforce_namespace_access as _enforce_namespace_access,
)
from .base import ToolHandler, logger


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

        _enforce_namespace_access(args["namespace"])

        try:
            api = _t._make_api()
            result = api.get_pages_from_namespace(args["namespace"])

            # Security: silently drop pages blocked by tag OR namespace, e.g. an
            # excluded sub-namespace (work/secret) under an allowed parent (work).
            if result:
                result = [
                    p for p in result
                    if not _is_page_blocked(p, p.get('originalName') or p.get('name') or '')
                ]

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
            return [TextContent(type="text", text=f"❌ Failed to get pages from namespace '{args['namespace']}': {str(e)}")]


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

        _enforce_namespace_access(args["namespace"])

        try:
            api = _t._make_api()
            result = api.get_pages_tree_from_namespace(args["namespace"])

            # Security: silently prune nodes blocked by tag OR namespace, e.g. an
            # excluded sub-namespace (work/secret) under an allowed parent (work).
            def prune_blocked(nodes):
                kept = []
                for node in nodes:
                    name = node.get('originalName') or node.get('name') or ''
                    if _is_page_blocked(node, name):
                        continue
                    children = node.get('children', [])
                    if children:
                        node = {**node, 'children': prune_blocked(children)}
                    kept.append(node)
                return kept

            if result:
                result = prune_blocked(result)

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
            return [TextContent(type="text", text=f"❌ Failed to get pages tree for namespace '{args['namespace']}': {str(e)}")]
