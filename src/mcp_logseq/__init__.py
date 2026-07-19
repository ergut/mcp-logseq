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
    p.add_argument("--insecure", action="store_true",
                   help=("Allow binding a non-loopback host over plain HTTP. Without TLS "
                         "the bearer token and all content travel unencrypted — only use "
                         "on a trusted network or behind a TLS-terminating reverse proxy."))
    return p.parse_args(argv)


def _validate_http_options(args) -> None:
    """Validate HTTP transport options. Raises SystemExit on misconfig.

    Checks that --tls-cert/--tls-key are supplied together, that both files
    exist on disk, and that a non-loopback host is not served over plain HTTP
    without --insecure.
    """
    import os
    if (args.tls_cert is None) != (args.tls_key is None):
        raise SystemExit("--tls-cert and --tls-key must be provided together")
    if args.tls_cert is not None:
        for label, path in (("--tls-cert", args.tls_cert), ("--tls-key", args.tls_key)):
            if not os.path.isfile(path):
                raise SystemExit(f"{label} file not found: {path}")

    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
    tls_enabled = args.tls_cert is not None
    if args.host not in _LOOPBACK_HOSTS and not tls_enabled and not args.insecure:
        raise SystemExit(
            f"Refusing to bind {args.host} over plain HTTP: the bearer token and "
            f"all content would travel unencrypted. Either provide --tls-cert/"
            f"--tls-key, put a TLS-terminating reverse proxy in front and bind a "
            f"loopback address, or pass --insecure to override (not recommended "
            f"outside a trusted network)."
        )


_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _setup_logging():
    """Configure process-wide logging for the CLI entrypoint.

    Level comes from LOGSEQ_LOG_LEVEL (default INFO). Logs go to stderr;
    a file handler is added only when LOGSEQ_LOG_FILE is set. Bad config
    never crashes the server: it degrades to INFO / stderr-only with a
    warning.
    """
    import logging
    import os
    import sys

    level_name = os.environ.get("LOGSEQ_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(level_name)
    invalid_level = not isinstance(level, int)
    if invalid_level:
        level = logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    log_file = os.environ.get("LOGSEQ_LOG_FILE")
    file_error = None
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file))
        except OSError as e:
            file_error = e

    logging.basicConfig(level=level, format=_LOG_FORMAT, handlers=handlers, force=True)

    logger = logging.getLogger("mcp-logseq")
    if invalid_level:
        logger.warning(
            f"Invalid LOGSEQ_LOG_LEVEL {level_name!r}; falling back to INFO"
        )
    if file_error is not None:
        logger.warning(
            f"Could not open LOGSEQ_LOG_FILE {log_file!r}: {file_error}; "
            f"logging to stderr only"
        )


def main():
    """Main entry point for the package."""
    import os

    _setup_logging()
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
# to keep package import light (the http path doesn't need it). Submodule
# access via ``from mcp_logseq.server import ...`` still works.
__all__ = ['main', 'parse_args']
