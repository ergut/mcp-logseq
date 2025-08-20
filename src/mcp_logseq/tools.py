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
