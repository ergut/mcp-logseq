"""HTTP (Streamable HTTP / SSE) ASGI transport for the LogSeq MCP server.

Wraps the MCP ``Server`` from :mod:`mcp_logseq.server` in a Starlette app and
serves it over the Streamable HTTP transport.

StreamableHTTPSessionManager (confirmed against installed mcp 1.27.2):
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    StreamableHTTPSessionManager(app, event_store=None, json_response=False,
                                 stateless=False, ...)
    async def handle_request(scope, receive, send) -> None
    def run() -> AsyncIterator[None]   # async context manager (task group)
"""

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from ..server import build_app


def create_asgi_app(auth_token: str, read_only: bool = False) -> Starlette:
    """Build a Starlette ASGI app serving the MCP server at ``/mcp``.

    Args:
        auth_token: Bearer token required on incoming requests.
        read_only: When True, the served app exposes only read tools (write
            tools are not registered).
    """
    app, _ = build_app(read_only=read_only)
    manager = StreamableHTTPSessionManager(app=app)

    async def handle(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    asgi = Starlette(routes=[Mount("/mcp", app=handle)], lifespan=lifespan)

    from .auth import BearerAuthMiddleware

    asgi.add_middleware(BearerAuthMiddleware, token=auth_token)
    return asgi


def run_http(
    host: str, port: int, auth_token: str, read_only: bool = False
) -> None:
    """Run the HTTP transport with uvicorn (imported lazily)."""
    import uvicorn

    uvicorn.run(
        create_asgi_app(auth_token, read_only=read_only), host=host, port=port
    )
