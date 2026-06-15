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
        # Compare as bytes: hmac.compare_digest rejects str with non-ASCII
        # chars, so a non-ASCII header would crash if compared as str.
        self._token = token.encode("utf-8")
        self._prefix = b"Bearer "

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # ASGI headers are a list of (name, value) tuples; duplicates are
        # permitted. Reject anything other than exactly one Authorization
        # header (zero = missing, >1 = ambiguous and last-wins-spoofable).
        auth_values = [
            value
            for name, value in (scope.get("headers") or [])
            if name == b"authorization"
        ]
        if len(auth_values) != 1:
            await self._unauthorized(scope, receive, send)
            return

        # Compare raw bytes (no decode): Bearer tokens are ASCII-only
        # (RFC 6750 token68), and a strict UTF-8 decode of garbage bytes would
        # otherwise raise and surface as a 500 instead of a clean 401.
        auth = auth_values[0]
        if not auth.startswith(self._prefix):
            await self._unauthorized(scope, receive, send)
            return
        presented = auth[len(self._prefix):]

        if not presented or not hmac.compare_digest(presented, self._token):
            await self._unauthorized(scope, receive, send)
            return

        await self._app(scope, receive, send)

    async def _unauthorized(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"error": "unauthorized"}, status_code=401)
        await response(scope, receive, send)
