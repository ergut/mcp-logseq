def parse_args(argv=None):
    """Build the CLI argument parser and parse ``argv``.

    Exposed separately so it can be unit-tested in isolation.
    """
    import argparse

    p = argparse.ArgumentParser(prog="mcp-logseq")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    # Loopback default; never bind to 0.0.0.0 implicitly.
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=12320)
    return p.parse_args(argv)


def main():
    """Main entry point for the package."""
    import os

    args = parse_args()
    if args.transport == "stdio":
        import asyncio

        from . import server

        asyncio.run(server.main())
    else:
        token = os.environ.get("MCP_HTTP_AUTH_TOKEN")
        if not token:
            raise SystemExit("MCP_HTTP_AUTH_TOKEN is required for --transport http")
        from .transport import http

        http.run_http(args.host, args.port, token)


# Optionally expose other important items at package level.
# ``server`` is intentionally NOT listed: it's imported lazily inside ``main``
# (eager import would trigger server.py's import-time LOGSEQ_API_TOKEN raise on
# the http path). Submodule access via ``from mcp_logseq.server import ...``
# still works.
__all__ = ['main', 'parse_args']
