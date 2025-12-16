import os
import logging
from . import logseq
from mcp.types import Tool, TextContent

logger = logging.getLogger("mcp-logseq")

api_key = os.getenv("LOGSEQ_API_TOKEN", "")
if api_key == "":
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")
else:
    logger.info("Found LOGSEQ_API_TOKEN in environment")
    logger.debug(f"API Token starts with: {api_key[:5]}...")

class ToolHandler():
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> list[TextContent]:
        raise NotImplementedError()

class CreatePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("create_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Create a new page in LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the new page"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the new page"
                    }
                },
                "required": ["title", "content"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "title" not in args or "content" not in args:
            raise RuntimeError("title and content arguments required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            api.create_page(args["title"], args["content"])
            
            return [TextContent(
                type="text",
                text=f"Successfully created page '{args['title']}'"
            )]
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
                        "default": False
                    }
                },
                "required": []
            }
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
                is_journal = page.get('journal?', False)
                if is_journal and not include_journals:
                    continue
                
                # Get page information
                name = page.get('originalName') or page.get('name', '<unknown>')
                
                # Build page info string
                info_parts = [f"- {name}"]
                if is_journal:
                    info_parts.append("[journal]")
                    
                pages_info.append(" ".join(info_parts))
            
            # Sort alphabetically by page name
            pages_info.sort()
            
            # Build response
            count_msg = f"\nTotal pages: {len(pages_info)}"
            journal_msg = " (excluding journal pages)" if not include_journals else " (including journal pages)"
            
            response = "LogSeq Pages:\n\n" + "\n".join(pages_info) + count_msg + journal_msg
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            logger.error(f"Failed to list pages: {str(e)}")
            raise

class GetPageContentToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("get_page_content")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get the content of a specific page from LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to retrieve"
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format (text or json)",
                        "enum": ["text", "json"],
                        "default": "text"
                    }
                },
                "required": ["page_name"]
            }
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
                return [TextContent(
                    type="text",
                    text=f"Page '{args['page_name']}' not found."
                )]

            # Handle JSON format request
            if args.get("format") == "json":
                return [TextContent(
                    type="text",
                    text=str(result)
                )]

            # Format as readable text
            content_parts = []
            
            # Get page info and blocks from the result structure
            page_info = result.get("page", {})
            blocks = result.get("blocks", [])
            
            # Title
            title = page_info.get("originalName", args["page_name"])
            content_parts.append(f"# {title}\n")
            
            # Properties
            properties = page_info.get("properties", {})
            if properties:
                content_parts.append("Properties:")
                for key, value in properties.items():
                    content_parts.append(f"- {key}: {value}")
                content_parts.append("")
            
            # Blocks content
            if blocks:
                content_parts.append("Content:")
                for block in blocks:
                    if isinstance(block, dict) and block.get("content"):
                        content_parts.append(f"- {block['content']}")
                    elif isinstance(block, str) and block.strip():
                        content_parts.append(f"- {block}")
            else:
                content_parts.append("No content blocks found.")
            
            return [TextContent(
                type="text",
                text="\n".join(content_parts)
            )]

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
                        "description": "Name of the page to delete"
                    }
                },
                "required": ["page_name"]
            }
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
                    success_msg += f"\n📋 Status: {result.get('message', 'Deletion confirmed')}"
            
            success_msg += f"\n🗑️  Page '{page_name}' has been permanently removed from LogSeq"
            
            return [TextContent(
                type="text",
                text=success_msg
            )]
        except ValueError as e:
            # Handle validation errors (page not found) gracefully
            return [TextContent(
                type="text", 
                text=f"❌ Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Failed to delete page: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to delete page '{args['page_name']}': {str(e)}"
            )]

class UpdatePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("update_page")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Update a page in LogSeq with new content and/or properties.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to update"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content to append to the page (optional)"
                    },
                    "properties": {
                        "type": "object",
                        "description": "Page properties to update (optional)",
                        "additionalProperties": True
                    }
                },
                "required": ["page_name"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument required")

        page_name = args["page_name"]
        content = args.get("content")
        properties = args.get("properties")
        
        # Validate that at least one update is provided
        if not content and not properties:
            return [TextContent(
                type="text",
                text="❌ Error: Either 'content' or 'properties' must be provided for update"
            )]

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.update_page(page_name, content=content, properties=properties)
            
            # Build detailed success message
            success_msg = f"✅ Successfully updated page '{page_name}'"
            
            # Show what was updated
            updates = result.get("updates", [])
            update_details = []
            
            for update_type, update_result in updates:
                if update_type == "properties":
                    update_details.append("📝 Properties updated")
                elif update_type == "properties_fallback":
                    update_details.append("📝 Properties updated (via fallback method)")
                elif update_type == "content":
                    update_details.append("📄 Content appended")
            
            if update_details:
                success_msg += f"\n{chr(10).join(update_details)}"
            
            success_msg += f"\n🔄 Page '{page_name}' has been updated in LogSeq"
            
            return [TextContent(
                type="text",
                text=success_msg
            )]
        except ValueError as e:
            # Handle validation errors (page not found) gracefully
            return [TextContent(
                type="text", 
                text=f"❌ Error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Failed to update page: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to update page '{page_name}': {str(e)}"
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
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 20
                    },
                    "include_blocks": {
                        "type": "boolean",
                        "description": "Include block content results",
                        "default": True
                    },
                    "include_pages": {
                        "type": "boolean", 
                        "description": "Include page name results",
                        "default": True
                    },
                    "include_files": {
                        "type": "boolean",
                        "description": "Include file name results", 
                        "default": False
                    }
                },
                "required": ["query"]
            }
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
                return [TextContent(
                    type="text",
                    text=f"No search results found for '{query}'"
                )]

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
                        content_parts.append(f"{i+1}. {content}")
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
                        snippet_text = snippet_text.replace("$pfts_2lqh>$", "").replace("$<pfts_2lqh$", "")
                        if len(snippet_text) > 200:
                            snippet_text = snippet_text[:200] + "..."
                        content_parts.append(f"{i+1}. {snippet_text}")
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
                content_parts.append("📌 *More results available - increase limit to see more*")

            # Summary
            total_results = len(result.get("blocks", [])) + len(result.get("pages", [])) + len(result.get("files", []))
            content_parts.append(f"\n**Total results found: {total_results}**")

            response_text = "\n".join(content_parts)
            
            return [TextContent(type="text", text=response_text)]
            
        except Exception as e:
            logger.error(f"Failed to search: {str(e)}")
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
