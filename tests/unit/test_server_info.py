from importlib.metadata import version

from mcp_logseq.server import build_app


def test_server_reports_package_version():
    server, _ = build_app()
    assert server.version == version("mcp-logseq")
