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
