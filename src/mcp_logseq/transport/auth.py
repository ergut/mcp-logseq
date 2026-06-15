"""Bearer token authentication middleware for the HTTP transport.

Pure ASGI middleware (intentionally NOT a ``BaseHTTPMiddleware`` subclass:
that base class buffers the response body and breaks the streaming/SSE that
Streamable HTTP relies on). Token comparison is constant-time via
:func:`hmac.compare_digest`.

Token source: the ``MCP_HTTP_AUTH_TOKEN`` env var (required in http mode) is
read by the caller (CLI wiring, Task 3) and passed in here as ``token``.
"""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Reject requests lacking a valid ``Authorization: Bearer <token>`` header."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        prefix = "Bearer "
        presented = auth[len(prefix):] if auth.startswith(prefix) else ""

        if not presented or not hmac.compare_digest(presented, self._token):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
