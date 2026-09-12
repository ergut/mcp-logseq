"""End-to-end coverage of the served MCP protocol surface (issue #92).

Every other test in this suite drives the tool handlers directly, so the wiring
between them and the SDK — the part mcp 2.0 changed — went untested until a user
started the server. Here a real ``ClientSession`` talks to the real ``Server``
over in-memory streams: ``initialize``, ``tools/list`` and ``tools/call`` all go
through the genuine SDK request pipeline.
"""

from contextlib import asynccontextmanager
from functools import partial

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import TextContent, Tool

from mcp_logseq.server import build_app, _WRITE_TOOL_NAMES
from mcp_logseq.tools import ToolHandler


class StubToolHandler(ToolHandler):
    """A tool with a typed schema that needs no Logseq API behind it."""

    def __init__(self):
        super().__init__("stub_tool")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Echo the given text, or fail on demand.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    def run_tool(self, args: dict):
        if args["text"] == "boom":
            raise RuntimeError("stub exploded")
        return [TextContent(type="text", text=f"echo: {args['text']}")]


@asynccontextmanager
async def _connected(read_only: bool = False):
    """Yield ``(session, handlers)`` for an initialized in-memory connection."""
    app, handlers = build_app(read_only=read_only)
    async with create_client_server_memory_streams() as (
        (client_read, client_write),
        (server_read, server_write),
    ):
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                partial(
                    app.run,
                    server_read,
                    server_write,
                    app.create_initialization_options(),
                    raise_exceptions=True,
                )
            )
            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                yield session, handlers
            tg.cancel_scope.cancel()


@pytest.mark.asyncio
async def test_initialize_and_list_tools():
    async with _connected() as (session, handlers):
        result = await session.list_tools()

    assert [t.name for t in result.tools] == list(handlers)
    assert all(t.input_schema["type"] == "object" for t in result.tools)


@pytest.mark.asyncio
async def test_read_only_app_serves_no_write_tools():
    async with _connected(read_only=True) as (session, _):
        result = await session.list_tools()

    assert _WRITE_TOOL_NAMES.isdisjoint({t.name for t in result.tools})


@pytest.mark.asyncio
async def test_call_tool_returns_handler_content():
    async with _connected() as (session, handlers):
        handlers["stub_tool"] = StubToolHandler()
        result = await session.call_tool("stub_tool", {"text": "hello"})

    assert result.is_error is False
    assert result.content[0].text == "echo: hello"


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_as_an_error_result():
    async with _connected() as (session, _):
        result = await session.call_tool("no_such_tool", {})

    assert result.is_error is True
    assert result.content[0].text == "Unknown tool: no_such_tool"


@pytest.mark.asyncio
async def test_handler_failure_reaches_the_client_verbatim():
    async with _connected() as (session, handlers):
        handlers["stub_tool"] = StubToolHandler()
        result = await session.call_tool("stub_tool", {"text": "boom"})

    assert result.is_error is True
    assert result.content[0].text == "Error: stub exploded"


@pytest.mark.asyncio
async def test_arguments_are_validated_against_the_tool_schema():
    async with _connected() as (session, handlers):
        handlers["stub_tool"] = StubToolHandler()
        missing = await session.call_tool("stub_tool", {})
        mistyped = await session.call_tool("stub_tool", {"text": 42})

    assert missing.is_error is True
    assert missing.content[0].text.startswith("Input validation error:")
    assert mistyped.is_error is True
    assert "42 is not of type 'string'" in mistyped.content[0].text
