"""Lazy, validated runtime configuration for the LogSeq API client.

All environment reading and validation lives here, in ``load_settings()``.
Importing this module (or any module that uses it) has no side effects;
validation happens at startup via ``get_settings()``, not at import time.
"""

import functools
import logging
import math
import os
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger("mcp-logseq")


@dataclass(frozen=True)
class Settings:
    """Resolved LogSeq API connection settings."""

    api_key: str
    protocol: str
    host: str
    port: int
    verify_ssl: bool
    connect_timeout: float
    read_timeout: float
    db_mode: bool

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)


def _parse_positive_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = float(raw_value)
    except ValueError:
        value = None

    if value is None or not math.isfinite(value) or value <= 0:
        logger.warning(
            f"{name} must be a positive number of seconds, got {raw_value!r}; "
            f"falling back to default {default}"
        )
        return default

    return value


def load_settings() -> Settings:
    """Read and validate configuration from the environment.

    Raises ``ValueError`` if ``LOGSEQ_API_TOKEN`` is missing.
    """
    api_key = os.getenv("LOGSEQ_API_TOKEN", "")
    if api_key == "":
        raise ValueError("LOGSEQ_API_TOKEN environment variable required")

    api_url = os.getenv("LOGSEQ_API_URL", "http://localhost:12315")
    parsed_url = urlparse(api_url)
    protocol = parsed_url.scheme or "http"

    verify_ssl_env = os.getenv("LOGSEQ_VERIFY_SSL")
    if verify_ssl_env is not None:
        verify_ssl = verify_ssl_env.lower() not in ("0", "false", "no")
    else:
        verify_ssl = protocol == "https"

    return Settings(
        api_key=api_key,
        protocol=protocol,
        host=parsed_url.hostname or "127.0.0.1",
        port=parsed_url.port or 12315,
        verify_ssl=verify_ssl,
        connect_timeout=_parse_positive_float_env("LOGSEQ_API_CONNECT_TIMEOUT", 3),
        read_timeout=_parse_positive_float_env("LOGSEQ_API_READ_TIMEOUT", 6),
        db_mode=os.getenv("LOGSEQ_DB_MODE", "").lower() in ("1", "true", "yes"),
    )


@functools.cache
def get_settings() -> Settings:
    """Return the process-wide ``Settings``, loading them on first use.

    Cached for the life of the process; call ``get_settings.cache_clear()``
    (tests) to force a reload from the environment.
    """
    return load_settings()
