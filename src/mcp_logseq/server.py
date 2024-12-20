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

# Configure logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp-logseq")

load_dotenv()

from . import tools

# Load environment variables
api_token = os.getenv("LOGSEQ_API_TOKEN")
if not api_token:
    logger.error("LOGSEQ_API_TOKEN not found in environment")
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")
else:
    logger.info("Found LOGSEQ_API_TOKEN in environment")

api_url = os.getenv("LOGSEQ_API_URL", "http://localhost:12315")
logger.info(f"Using API URL: {api_url}")

app = Server("mcp-logseq")

tool_handlers = {}
def add_tool_handler(tool_class: tools.ToolHandler):
    global tool_handlers
    logger.debug(f"Registering tool handler: {tool_class.name}")
    tool_handlers[tool_class.name] = tool_class

def get_tool_handler(name: str) -> tools.ToolHandler | None:
    logger.debug(f"Looking for tool handler: {name}")
    if name not in tool_handlers:
        logger.warning(f"Tool handler not found: {name}")
        return None
    
    return tool_handlers[name]

# Register all tool handlers
add_tool_handler(tools.CreatePageToolHandler())
add_tool_handler(tools.ListPagesToolHandler())

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    logger.debug("Listing tools")
    return [th.get_tool_description() for th in tool_handlers.values()]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    logger.info(f"Tool call: {name} with arguments {arguments}")
    
    if not isinstance(arguments, dict):
        logger.error("Arguments must be dictionary")
        raise RuntimeError("arguments must be dictionary")

    tool_handler = get_tool_handler(name)
    if not tool_handler:
        logger.error(f"Unknown tool: {name}")
        raise ValueError(f"Unknown tool: {name}")

    try:
        logger.debug(f"Running tool {name}")
        return tool_handler.run_tool(arguments)
    except Exception as e:
        logger.error(f"Error running tool: {str(e)}")
        raise RuntimeError(f"Caught Exception. Error: {str(e)}")

async def main():
    logger.info("Starting LogSeq MCP server")
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
