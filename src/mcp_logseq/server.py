import json
import logging
from collections.abc import Sequence
from typing import Any
import os
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

load_dotenv()

from . import tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-logseq")

# Load environment variables
api_token = os.getenv("LOGSEQ_API_TOKEN")
if not api_token:
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")

api_url = os.getenv("LOGSEQ_API_URL", "http://localhost:12315")

app = Server("mcp-logseq")

tool_handlers = {}
def add_tool_handler(tool_class: tools.ToolHandler):
    global tool_handlers
    tool_handlers[tool_class.name] = tool_class

def get_tool_handler(name: str) -> tools.ToolHandler | None:
    if name not in tool_handlers:
        return None
    
    return tool_handlers[name]

# Register all tool handlers
add_tool_handler(tools.ListGraphsToolHandler())
add_tool_handler(tools.ListPagesToolHandler())
add_tool_handler(tools.GetPageContentToolHandler())
add_tool_handler(tools.SearchToolHandler())
add_tool_handler(tools.CreatePageToolHandler())
add_tool_handler(tools.UpdatePageToolHandler())
add_tool_handler(tools.DeletePageToolHandler())

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [th.get_tool_description() for th in tool_handlers.values()]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    
    if not isinstance(arguments, dict):
        raise RuntimeError("arguments must be dictionary")

    tool_handler = get_tool_handler(name)
    if not tool_handler:
        raise ValueError(f"Unknown tool: {name}")

    try:
        return tool_handler.run_tool(arguments)
    except Exception as e:
        logger.error(str(e))
        raise RuntimeError(f"Caught Exception. Error: {str(e)}")

async def main():
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
