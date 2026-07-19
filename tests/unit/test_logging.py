"""Tests for logging configuration (A5): entrypoint setup, import purity, redaction."""

import logging

import pytest

import mcp_logseq


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
