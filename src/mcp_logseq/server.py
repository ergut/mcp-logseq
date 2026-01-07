import json
import logging
import sys
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

# Configure logging to stderr with more verbose output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp-logseq")

# Add a file handler to keep logs (in user's home directory to avoid permission issues)
import tempfile

log_dir = os.path.expanduser("~/.cache/mcp-logseq")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "mcp_logseq.log")
try:
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.debug(f"Logging to: {log_file}")
except Exception as e:
    # If file logging fails, continue without it
    logger.warning(f"Could not setup file logging: {e}")
    pass

load_dotenv()

from . import tools

# Load environment variables with more verbose logging
api_token = os.getenv("LOGSEQ_API_TOKEN")
if not api_token:
    logger.error("LOGSEQ_API_TOKEN not found in environment")
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")
else:
    logger.info("Found LOGSEQ_API_TOKEN in environment")
    logger.debug("API token validation successful")

api_url = os.getenv("LOGSEQ_API_URL", "http://localhost:12315")
logger.info(f"Using API URL: {api_url}")

app = Server("mcp-logseq")

tool_handlers = {}


def add_tool_handler(tool_class: tools.ToolHandler):
    global tool_handlers
    logger.debug(f"Registering tool handler: {tool_class.name}")
    tool_handlers[tool_class.name] = tool_class
    logger.info(f"Successfully registered tool handler: {tool_class.name}")


def get_tool_handler(name: str) -> tools.ToolHandler | None:
    logger.debug(f"Looking for tool handler: {name}")
    handler = tool_handlers.get(name)
    if handler is None:
        logger.warning(f"Tool handler not found: {name}")
    else:
        logger.debug(f"Found tool handler: {name}")
    return handler


# Register all tool handlers
logger.info("Registering tool handlers...")

add_tool_handler(tools.CreatePageToolHandler())
add_tool_handler(tools.UpdatePageToolHandler())
add_tool_handler(tools.ListPagesToolHandler())
add_tool_handler(tools.GetPageContentToolHandler())
add_tool_handler(tools.DeletePageToolHandler())
add_tool_handler(tools.SearchToolHandler())

logger.info("Tool handlers registration complete")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    logger.debug("Listing tools")
    tools_list = [th.get_tool_description() for th in tool_handlers.values()]
    logger.debug(f"Found {len(tools_list)} tools")
    return tools_list


@app.call_tool()
async def call_tool(
    name: str, arguments: Any
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
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
        result = tool_handler.run_tool(arguments)
        logger.debug(f"Tool result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error running tool: {str(e)}", exc_info=True)
        raise RuntimeError(f"Error: {str(e)}")


async def main():
    logger.info("Starting LogSeq MCP server")
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Initializing server...")
        await app.run(read_stream, write_stream, app.create_initialization_options())
