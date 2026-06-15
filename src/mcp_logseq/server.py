import asyncio
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

def _register_all_tool_handlers(handlers: dict) -> None:
    """Populate ``handlers`` with every available ToolHandler instance.

    Mutates the provided dict in place so callers can wire ``list_tools`` /
    ``call_tool`` closures over the same registry.
    """

    def add(tool_class: tools.ToolHandler) -> None:
        logger.debug(f"Registering tool handler: {tool_class.name}")
        handlers[tool_class.name] = tool_class
        logger.info(f"Successfully registered tool handler: {tool_class.name}")

    logger.info("Registering tool handlers...")

    add(tools.CreatePageToolHandler())
    add(tools.UpdatePageToolHandler())
    add(tools.ListPagesToolHandler())
    add(tools.GetPageContentToolHandler())
    add(tools.DeletePageToolHandler())
    add(tools.DeleteBlockToolHandler())
    add(tools.UpdateBlockToolHandler())
    add(tools.GetBlockToolHandler())
    add(tools.SearchToolHandler())
    add(tools.QueryToolHandler())
    add(tools.FindPagesByPropertyToolHandler())
    add(tools.GetPagesFromNamespaceToolHandler())
    add(tools.GetPagesTreeFromNamespaceToolHandler())
    add(tools.RenamePageToolHandler())
    add(tools.GetPageBacklinksToolHandler())
    add(tools.InsertNestedBlockToolHandler())
    add(tools.SetBlockPropertiesToolHandler())
    logger.info("Tool handlers registration complete")

    # Conditional vector tool registration — only when LOGSEQ_CONFIG_FILE is set
    # and vector.enabled is true in the config file
    try:
        from .config import load_vector_config, load_exclude_tags
        vector_config = load_vector_config()
        # Merge top-level exclude_tags into vector config (additive union)
        top_level_exclude = load_exclude_tags()
        if vector_config and top_level_exclude:
            merged = list(dict.fromkeys(top_level_exclude + vector_config.exclude_tags))
            vector_config.exclude_tags = merged
        if vector_config and vector_config.enabled:
            from .vector.index import (
                VectorDBStatusToolHandler,
                VectorSearchToolHandler,
                SyncVectorDBToolHandler,
            )
            add(VectorSearchToolHandler(vector_config))
            add(SyncVectorDBToolHandler(vector_config))
            add(VectorDBStatusToolHandler(vector_config))
            logger.info("Vector search tools registered (3 tools)")
        else:
            logger.debug("Vector search not configured — skipping vector tools")
    except Exception as e:
        logger.warning(f"Could not load vector config, vector tools disabled: {e}")


def build_app(read_only: bool = False) -> Server:
    """Build a fully wired MCP ``Server`` with all tool handlers registered.

    ``read_only`` is accepted for forward compatibility (Task 5 will use it to
    skip write tools); it is currently ignored and all tools are registered.
    """
    server = Server("mcp-logseq")
    handlers: dict = {}
    _register_all_tool_handlers(handlers)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        logger.debug("Listing tools")
        tools_list = [th.get_tool_description() for th in handlers.values()]
        logger.debug(f"Found {len(tools_list)} tools")
        return tools_list

    @server.call_tool()
    async def call_tool(
        name: str, arguments: Any
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """Handle tool calls."""
        logger.info(f"Tool call: {name} with arguments {arguments}")

        if not isinstance(arguments, dict):
            logger.error("Arguments must be dictionary")
            raise RuntimeError("arguments must be dictionary")

        tool_handler = handlers.get(name)
        if not tool_handler:
            logger.error(f"Unknown tool: {name}")
            raise ValueError(f"Unknown tool: {name}")

        try:
            logger.debug(f"Running tool {name}")
            result = await asyncio.to_thread(tool_handler.run_tool, arguments)
            logger.debug(f"Tool result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error running tool: {str(e)}", exc_info=True)
            raise RuntimeError(f"Error: {str(e)}")

    return server


# ---------------------------------------------------------------------------
# Backward-compatible module-level surface.
#
# Existing code/tests import ``app``, ``tool_handlers``, ``add_tool_handler``
# and ``get_tool_handler`` from this module. Keep them working by exposing a
# module-level Server plus its registry.
# ---------------------------------------------------------------------------

app = build_app()
tool_handlers: dict = {}
_register_all_tool_handlers(tool_handlers)


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


async def main():
    logger.info("Starting LogSeq MCP server")
    from mcp.server.stdio import stdio_server

    app = build_app()
    async with stdio_server() as (read_stream, write_stream):
        logger.info("Initializing server...")
        await app.run(read_stream, write_stream, app.create_initialization_options())
