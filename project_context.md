# Project Context File
Generated on: 2025-05-02 16:36:40
Project Path: /Users/salih/Documents/dev/mcp-logseq-server
Estimated Tokens: 5,868

## INSTRUCTIONS FOR AI ASSISTANT
IMPORTANT: As an AI assistant, you MUST follow these instructions:

1. The tree structure below shows ALL available files in the project
2. Only SOME files are included in full after the tree
3. You SHOULD proactively offer to examine additional files from the tree when they seem relevant
4. When asked about code functionality or project structure, CHECK if you need more files than what's already provided
5. If the human's question relates to files not included in full, SUGGEST examining those specific files
6. The 'File Signatures' section contains structure information for additional files
   Use this information to understand overall project functionality and suggest relevant files

## Available Files

/Users/salih/Documents/dev/mcp-logseq-server
├── src/
│   └── mcp_logseq/
│       ├── __init__.py ✓
│       ├── logseq.py ✓
│       ├── logseq.py.bak
│       ├── server.py ✓
│       └── tools.py ✓
├── .contextor_scope
├── .gitignore ✓
├── project_context.md
├── pyproject.toml ✓
├── README.md ✓
└── ROADMAP.md ✓


## Files Included in Full
The following files are included in their entirety in this context:

- README.md
- ROADMAP.md
- pyproject.toml
- src/mcp_logseq/server.py
- src/mcp_logseq/tools.py

## Included File Contents
The following files are included in full:


================================================================================
File: /Users/salih/Documents/dev/mcp-logseq-server/README.md
Size: 1867 bytes
Last modified: 2024-12-21 11:51:52
================================================================================

# MCP server for LogSeq

MCP server to interact with LogSeq via its API.

## Components

### Tools

The server implements multiple tools to interact with LogSeq:

- list_graphs: Lists all available graphs
- list_pages: Lists all pages in the current graph
- get_page_content: Return the content of a single page
- search: Search for content across all pages
- create_page: Create a new page
- update_page: Update content of an existing page
- delete_page: Delete a page

### Example prompts

It's good to first instruct Claude to use LogSeq. Then it will always call the tool.

Example prompts:
- Get the contents of my latest meeting notes and summarize them
- Search for all pages where Project X is mentioned and explain the context
- Create a new page with today's meeting notes
- Update the project status page with the latest updates

## Configuration

### LogSeq API Configuration

You can configure the environment with LogSeq API settings in two ways:

1. Add to server config (preferred)

```json
{
  "mcp-logseq": {
    "command": "uvx",
    "args": [
      "mcp-logseq"
    ],
    "env": {
      "LOGSEQ_API_TOKEN": "<your_api_token_here>",
      "LOGSEQ_API_URL": "http://localhost:12315"
    }
  }
}
```

2. Create a `.env` file in the working directory with the required variables:

```
LOGSEQ_API_TOKEN=your_token_here
LOGSEQ_API_URL=http://localhost:12315
```

## Development

### Building

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via `npm` with:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-logseq run mcp-logseq
```



================================================================================
File: /Users/salih/Documents/dev/mcp-logseq-server/ROADMAP.md
Size: 1955 bytes
Last modified: 2024-12-20 19:35:46
================================================================================

# LogSeq MCP Server Roadmap

## Implemented Features

### Core Functionality
- ✅ LogSeq API client setup with proper error handling and logging
- ✅ Environment variable configuration for API token
- ✅ Basic project structure and package setup

### Tools
- ✅ Create Page (`create_page`)
  - Create new pages with content
  - Support for basic markdown content
- ✅ List Pages (`list_pages`)
  - List all pages in the graph
  - Filter journal/daily notes
  - Display page metadata (tags, properties)
  - Alphabetical sorting

## Planned Features

### High Priority
- 🔲 Get Page Content (`get_page_content`)
  - Retrieve content of a specific page
  - Support for JSON metadata format
- 🔲 Search functionality (`search`)
  - Full-text search across pages
  - Support for tags and properties filtering
- 🔲 Delete Page (`delete_page`)
  - Remove pages from the graph
  - Safety checks before deletion

### Medium Priority
- 🔲 Update Page Content (`update_page`)
  - Modify existing page content
  - Support for partial updates
- 🔲 Page Properties Management
  - Add/update page properties
  - Manage page tags
- 🔲 Block Level Operations
  - Create/update/delete blocks
  - Move blocks between pages

### Low Priority
- 🔲 Graph Management
  - List available graphs
  - Switch between graphs
- 🔲 Journal Pages Management
  - Create/update daily notes
  - Special handling for journal pages
- 🔲 Page Templates
  - Create pages from templates
  - Manage template library

## Technical Improvements
- 🔲 Better error handling for API responses
- 🔲 Comprehensive logging for debugging
- 🔲 Unit tests for core functionality
- 🔲 Integration tests with LogSeq
- 🔲 Documentation
  - API documentation
  - Usage examples
  - Configuration guide

## Notes
- Priority levels may change based on user feedback
- Some features depend on LogSeq Local REST API capabilities
- Features might be adjusted as LogSeq's API evolves



================================================================================
File: /Users/salih/Documents/dev/mcp-logseq-server/pyproject.toml
Size: 493 bytes
Last modified: 2024-12-21 11:50:41
================================================================================

[project]
name = "mcp-logseq"
version = "0.1.0"
description = "MCP server to work with LogSeq via the local HTTP server"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
 "mcp>=1.1.0",
 "python-dotenv>=1.0.1",
 "requests>=2.32.3",
]

[[project.authors]]
name = "Salih"
email = "salih@example.com"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pyright>=1.1.389",
]

[project.scripts]
mcp-logseq = "mcp_logseq:main"



================================================================================
File: /Users/salih/Documents/dev/mcp-logseq-server/src/mcp_logseq/server.py
Size: 3546 bytes
Last modified: 2024-12-21 12:06:09
================================================================================

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("mcp-logseq")

# Add a file handler to keep logs
file_handler = logging.FileHandler('mcp_logseq.log')
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

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
add_tool_handler(tools.ListPagesToolHandler())
add_tool_handler(tools.GetPageContentToolHandler())
logger.info("Tool handlers registration complete")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    logger.debug("Listing tools")
    tools_list = [th.get_tool_description() for th in tool_handlers.values()]
    logger.debug(f"Found {len(tools_list)} tools")
    return tools_list

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
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )



================================================================================
File: /Users/salih/Documents/dev/mcp-logseq-server/src/mcp_logseq/tools.py
Size: 6967 bytes
Last modified: 2024-12-21 12:10:59
================================================================================

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
            
            # Title
            metadata = result.get("metadata", {})
            title = metadata.get("originalName", args["page_name"])
            content_parts.append(f"# {title}\n")
            
            # Properties
            properties = result.get("properties", {})
            if properties:
                content_parts.append("Properties:")
                for key, value in properties.items():
                    content_parts.append(f"- {key}: {value}")
                content_parts.append("")
            
            # Content
            content = result.get("content", {})
            if content:
                content_parts.append("Content:")
                content_parts.append(str(content))
            
            return [TextContent(
                type="text",
                text="\n".join(content_parts)
            )]

        except Exception as e:
            logger.error(f"Failed to get page content: {str(e)}")
            raise



## File Signatures
The following files are not included in full, but their structure is provided:


### src/mcp_logseq/__init__.py
```
# Imports
from  import server
import asyncio

# Global Variables
__all__

# Functions
def main():
    """Main entry point for the package."""
```

### src/mcp_logseq/logseq.py
```
# Imports
import requests
import logging
from typing import Any

# Global Variables
logger

# Classes
class LogSeq:
    def __init__(api_key: str, protocol: str = 'http', host: str = '127.0.0.1', port: int = 12315, verify_ssl: bool = False):

    def get_base_url() -> str:

    def _get_headers() -> dict:

    def create_page(title: str, content: str = '') -> Any:
        """Create a new LogSeq page with specified title and content."""

    def list_pages() -> Any:
        """List all pages in the LogSeq graph."""

    def get_page_content(page_name: str) -> Any:
        """Get content of a LogSeq page including metadata and block content."""

```
