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
    p.add_argument(
        "--read-only",
        action="store_true",
        help="Disable write tools (create/update/delete/rename for pages and blocks).",
    )
    p.add_argument("--tls-cert", default=None,
                   help="Path to a PEM TLS certificate. Enables HTTPS (requires --tls-key).")
    p.add_argument("--tls-key", default=None,
                   help="Path to the PEM TLS private key (requires --tls-cert).")
    return p.parse_args(argv)


def _validate_http_options(args) -> None:
    """Validate TLS options for the http transport. Raises SystemExit on misconfig.

    Task 2 extends this with the insecure-bind guardrail.
    """
    import os
    if (args.tls_cert is None) != (args.tls_key is None):
        raise SystemExit("--tls-cert and --tls-key must be provided together")
    if args.tls_cert is not None:
        for label, path in (("--tls-cert", args.tls_cert), ("--tls-key", args.tls_key)):
            if not os.path.isfile(path):
                raise SystemExit(f"{label} file not found: {path}")


def main():
    """Main entry point for the package."""
    import os

    args = parse_args()
    if args.transport == "stdio":
        import asyncio

        from . import server

        asyncio.run(server.main(read_only=args.read_only))
    else:
        token = os.environ.get("MCP_HTTP_AUTH_TOKEN")
        if not token:
            raise SystemExit("MCP_HTTP_AUTH_TOKEN is required for --transport http")
        _validate_http_options(args)
        from .transport import http

        http.run_http(args.host, args.port, token, read_only=args.read_only,
                      tls_cert=args.tls_cert, tls_key=args.tls_key)


# Optionally expose other important items at package level.
# ``server`` is intentionally NOT listed: it's imported lazily inside ``main``
# (eager import would trigger server.py's import-time LOGSEQ_API_TOKEN raise on
# the http path). Submodule access via ``from mcp_logseq.server import ...``
# still works.
__all__ = ['main', 'parse_args']
