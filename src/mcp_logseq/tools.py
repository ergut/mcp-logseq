from collections.abc import Sequence
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import json
import os
from . import logseq

api_token = os.getenv("LOGSEQ_API_TOKEN", "")
api_url = os.getenv("LOGSEQ_API_URL", "http://localhost:12315")

if api_token == "":
    raise ValueError("LOGSEQ_API_TOKEN environment variable required")

TOOL_LIST_GRAPHS = "list_graphs"
TOOL_LIST_PAGES = "list_pages"
TOOL_GET_PAGE_CONTENT = "get_page_content"
TOOL_SEARCH = "search"
TOOL_CREATE_PAGE = "create_page"
TOOL_UPDATE_PAGE = "update_page"
TOOL_DELETE_PAGE = "delete_page"

class ToolHandler():
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()

class ListGraphsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_GRAPHS)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all available LogSeq graphs.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        graphs = api.list_graphs()

        return [
            TextContent(
                type="text",
                text=json.dumps(graphs, indent=2)
            )
        ]

class ListPagesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_PAGES)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all pages in a LogSeq graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_name": {
                        "type": "string",
                        "description": "Optional name of the graph to list pages from"
                    }
                },
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        pages = api.list_pages(args.get("graph_name"))

        return [
            TextContent(
                type="text",
                text=json.dumps(pages, indent=2)
            )
        ]

class GetPageContentToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_GET_PAGE_CONTENT)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the content of a single page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to get content from"
                    },
                    "graph_name": {
                        "type": "string",
                        "description": "Optional name of the graph containing the page"
                    }
                },
                "required": ["page_name"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument missing in arguments")

        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        content = api.get_page_content(args["page_name"], args.get("graph_name"))

        return [
            TextContent(
                type="text",
                text=json.dumps(content, indent=2)
            )
        ]

class SearchToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_SEARCH)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Search for content across all pages in LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise RuntimeError("query argument missing in arguments")

        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        results = api.search(args["query"])

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]

class CreatePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_CREATE_PAGE)

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
                    },
                    "graph_name": {
                        "type": "string",
                        "description": "Optional name of the graph to create the page in"
                    }
                },
                "required": ["title", "content"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "title" not in args or "content" not in args:
            raise RuntimeError("title and content arguments required")

        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        result = api.create_page(
            args["title"],
            args["content"],
            args.get("graph_name")
        )

        return [
            TextContent(
                type="text",
                text=f"Successfully created page '{args['title']}'"
            )
        ]

class UpdatePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_UPDATE_PAGE)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Update content of an existing page in LogSeq.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to update"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content for the page"
                    },
                    "graph_name": {
                        "type": "string",
                        "description": "Optional name of the graph containing the page"
                    }
                },
                "required": ["page_name", "content"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "page_name" not in args or "content" not in args:
            raise RuntimeError("page_name and content arguments required")

        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        result = api.update_page(
            args["page_name"],
            args["content"],
            args.get("graph_name")
        )

        return [
            TextContent(
                type="text",
                text=f"Successfully updated page '{args['page_name']}'"
            )
        ]

class DeletePageToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_DELETE_PAGE)

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
                    },
                    "graph_name": {
                        "type": "string",
                        "description": "Optional name of the graph containing the page"
                    }
                },
                "required": ["page_name"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "page_name" not in args:
            raise RuntimeError("page_name argument missing in arguments")

        api = logseq.LogSeq(api_token=api_token, api_url=api_url)
        api.delete_page(args["page_name"], args.get("graph_name"))

        return [
            TextContent(
                type="text",
                text=f"Successfully deleted page '{args['page_name']}'"
            )
        ]
