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
        logger.info(f"Creating page with args: {args}")
        
        if "title" not in args or "content" not in args:
            logger.error("Missing required arguments")
            raise RuntimeError("title and content arguments required")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.create_page(args["title"], args["content"])
            
            logger.info("Successfully created page")
            logger.debug(f"API response: {result}")

            return [
                TextContent(
                    type="text",
                    text=f"Successfully created page '{args['title']}'"
                )
            ]
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
                "properties": {},
                "required": []
            }
        )
