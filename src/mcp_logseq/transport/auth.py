"""Bearer token authentication middleware for the HTTP transport.

NOTE: This is a MINIMAL placeholder added in Task 1 so ``transport/http.py``
imports cleanly and the route can enforce a 401 for missing/invalid tokens.
Task 2 will replace/extend this with the full bearer-auth implementation
(constant-time comparison, scheme validation, structured error bodies, etc.).
"""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Reject requests lacking a valid ``Authorization: Bearer <token>`` header.

    Minimal implementation: compares the presented token against the configured
    ``token`` and returns 401 on mismatch. Hardened in Task 2.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        header = request.headers.get("authorization", "")
        expected = f"Bearer {self.token}"

        if header != expected:
            response = JSONResponse(
                {"error": "unauthorized"}, status_code=401
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
