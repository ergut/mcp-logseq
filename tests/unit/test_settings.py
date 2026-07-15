"""Tests for mcp_logseq.settings — lazy, validated configuration.

Covers the A1 refactor: importing the package must have no env side effects;
all env reading and validation happens in ``load_settings()`` /
``get_settings()`` at startup, not at import time.
"""

import os
import subprocess
import sys

import pytest

from mcp_logseq import settings

_ENV_VARS = (
    "LOGSEQ_API_TOKEN",
    "LOGSEQ_API_URL",
    "LOGSEQ_VERIFY_SSL",
    "LOGSEQ_API_CONNECT_TIMEOUT",
    "LOGSEQ_API_READ_TIMEOUT",
    "LOGSEQ_DB_MODE",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all settings-related env vars and reset the settings cache."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    settings.get_settings.cache_clear()
    yield monkeypatch
    settings.get_settings.cache_clear()


class TestImportHasNoSideEffects:
    def test_import_without_token_succeeds(self):
        """Importing tools/server must not require LOGSEQ_API_TOKEN (A1)."""
        env = {k: v for k, v in os.environ.items() if k not in _ENV_VARS}
        result = subprocess.run(
            [sys.executable, "-c", "import mcp_logseq.tools, mcp_logseq.server"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


class TestLoadSettings:
    def test_missing_token_raises(self, clean_env):
        with pytest.raises(ValueError, match="LOGSEQ_API_TOKEN"):
            settings.load_settings()

    def test_defaults(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        s = settings.load_settings()
        assert s.api_key == "tok"
        assert s.protocol == "http"
        assert s.host == "localhost"
        assert s.port == 12315
        assert s.verify_ssl is False  # plain http → no TLS verification
        assert s.timeout == (3, 6)
        assert s.db_mode is False

    def test_api_url_parsed(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        clean_env.setenv("LOGSEQ_API_URL", "https://logseq.example.com:8443")
        s = settings.load_settings()
        assert s.protocol == "https"
        assert s.host == "logseq.example.com"
        assert s.port == 8443
        assert s.verify_ssl is True  # https → verify by default

    def test_verify_ssl_env_overrides_protocol_default(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        clean_env.setenv("LOGSEQ_API_URL", "https://logseq.example.com:8443")
        clean_env.setenv("LOGSEQ_VERIFY_SSL", "false")
        assert settings.load_settings().verify_ssl is False

    def test_db_mode_env(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        clean_env.setenv("LOGSEQ_DB_MODE", "true")
        assert settings.load_settings().db_mode is True

    def test_timeout_overrides(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        clean_env.setenv("LOGSEQ_API_CONNECT_TIMEOUT", "2.5")
        clean_env.setenv("LOGSEQ_API_READ_TIMEOUT", "15")
        assert settings.load_settings().timeout == (2.5, 15.0)

    def test_invalid_timeout_falls_back_to_default(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok")
        clean_env.setenv("LOGSEQ_API_READ_TIMEOUT", "not-a-number")
        assert settings.load_settings().timeout == (3, 6)


class TestGetSettingsCache:
    def test_cached_across_env_changes(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok-1")
        first = settings.get_settings()
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok-2")
        assert settings.get_settings() is first

    def test_cache_clear_picks_up_new_env(self, clean_env):
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok-1")
        settings.get_settings()
        clean_env.setenv("LOGSEQ_API_TOKEN", "tok-2")
        settings.get_settings.cache_clear()
        assert settings.get_settings().api_key == "tok-2"
