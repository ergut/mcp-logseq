"""Tests for logging configuration (A5): entrypoint setup, import purity, redaction."""

import asyncio
import logging
import subprocess
import sys

import pytest
from mcp.types import TextContent

import mcp_logseq


def test_importing_server_does_not_configure_logging():
    """Importing mcp_logseq.server must not touch root-logger config (A5).

    Runs in a subprocess because this test process has long since imported
    the module and configured logging itself.
    """
    code = (
        "import logging, sys\n"
        "import mcp_logseq.server\n"
        "root = logging.getLogger()\n"
        "assert root.level == logging.WARNING, f'root level changed: {root.level}'\n"
        "assert root.handlers == [], f'root handlers added: {root.handlers}'\n"
        "pkg = logging.getLogger('mcp-logseq')\n"
        "assert pkg.handlers == [], f'package handlers added: {pkg.handlers}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def clean_root_logger():
    """Snapshot and restore root logger handlers/level around a test.

    _setup_logging() uses basicConfig(force=True), which would otherwise leak
    handler changes into the rest of the test session.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield root
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


class TestSetupLogging:
    def test_default_level_is_info(self, monkeypatch, clean_root_logger):
        monkeypatch.delenv("LOGSEQ_LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOGSEQ_LOG_FILE", raising=False)
        mcp_logseq._setup_logging()
        assert clean_root_logger.level == logging.INFO

    def test_level_env_var_honored(self, monkeypatch, clean_root_logger):
        monkeypatch.setenv("LOGSEQ_LOG_LEVEL", "debug")  # case-insensitive
        monkeypatch.delenv("LOGSEQ_LOG_FILE", raising=False)
        mcp_logseq._setup_logging()
        assert clean_root_logger.level == logging.DEBUG

    def test_invalid_level_falls_back_to_info(self, monkeypatch, clean_root_logger, capsys):
        monkeypatch.setenv("LOGSEQ_LOG_LEVEL", "VERBOSE")
        monkeypatch.delenv("LOGSEQ_LOG_FILE", raising=False)
        mcp_logseq._setup_logging()
        assert clean_root_logger.level == logging.INFO
        # The warning about the bad value goes to the stderr handler just set up.
        assert "VERBOSE" in capsys.readouterr().err

    def test_no_file_handler_by_default(self, monkeypatch, clean_root_logger):
        monkeypatch.delenv("LOGSEQ_LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOGSEQ_LOG_FILE", raising=False)
        mcp_logseq._setup_logging()
        assert not any(
            isinstance(h, logging.FileHandler) for h in clean_root_logger.handlers
        )

    def test_log_file_env_var_adds_file_handler(self, monkeypatch, clean_root_logger, tmp_path):
        log_path = tmp_path / "mcp.log"
        monkeypatch.delenv("LOGSEQ_LOG_LEVEL", raising=False)
        monkeypatch.setenv("LOGSEQ_LOG_FILE", str(log_path))
        mcp_logseq._setup_logging()
        file_handlers = [
            h for h in clean_root_logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_path)
        logging.getLogger("mcp-logseq").info("hello file")
        for h in file_handlers:
            h.close()
        assert "hello file" in log_path.read_text()

    def test_unopenable_log_file_degrades_to_stderr(self, monkeypatch, clean_root_logger, tmp_path, capsys):
        monkeypatch.delenv("LOGSEQ_LOG_LEVEL", raising=False)
        # A path whose parent directory does not exist cannot be opened.
        monkeypatch.setenv("LOGSEQ_LOG_FILE", str(tmp_path / "no-such-dir" / "mcp.log"))
        mcp_logseq._setup_logging()  # must not raise
        assert not any(
            isinstance(h, logging.FileHandler) for h in clean_root_logger.handlers
        )
        assert "LOGSEQ_LOG_FILE" in capsys.readouterr().err


class _FakeHandler:
    def run_tool(self, arguments):
        return [TextContent(type="text", text="SECRET-RESULT-BODY")]


class TestDispatchRedaction:
    def test_argument_and_result_bodies_not_logged(self, caplog):
        from mcp_logseq.server import _dispatch_tool_call

        with caplog.at_level(logging.DEBUG, logger="mcp-logseq"):
            result = asyncio.run(
                _dispatch_tool_call(
                    {"fake_tool": _FakeHandler()},
                    "fake_tool",
                    {"title": "T", "content": "SECRET-ARG-VALUE"},
                )
            )

        assert len(result) == 1
        # Identifiers are logged...
        assert "fake_tool" in caplog.text
        assert "content, title" in caplog.text  # sorted argument keys
        assert "1 content item(s)" in caplog.text
        # ...bodies are not.
        assert "SECRET-ARG-VALUE" not in caplog.text
        assert "SECRET-RESULT-BODY" not in caplog.text

    def test_unknown_tool_still_raises_value_error(self):
        from mcp_logseq.server import _dispatch_tool_call

        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.run(_dispatch_tool_call({}, "nope", {}))

    def test_non_dict_arguments_still_raise_runtime_error(self):
        from mcp_logseq.server import _dispatch_tool_call

        with pytest.raises(RuntimeError, match="arguments must be dictionary"):
            asyncio.run(_dispatch_tool_call({}, "any", "not-a-dict"))
