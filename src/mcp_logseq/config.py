"""
Config file loading for mcp-logseq.

Set LOGSEQ_CONFIG_FILE to a path pointing to a JSON config file.
If not set, or if vector.enabled is false/missing, vector tools are not loaded.

Example config.json:
{
  "logseq_graph_path": "/path/to/logseq/pages",
  "exclude_tags": ["private", "secret"],
  "include_namespaces": ["work", "projects"],
  "exclude_namespaces": ["work/secret"],
  "vector": {
    "enabled": true,
    "db_path": "~/.logseq-vector",
    "embedder": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "base_url": "http://localhost:11434"
    },
    "include_journals": true,
    "exclude_tags": ["private"],
    "include_namespaces": ["work"],
    "exclude_namespaces": ["work/secret"],
    "min_chunk_length": 50,
    "watch_debounce_ms": 5000
  }
}

The vector-block "include_namespaces" / "exclude_namespaces" are INDEX-TIME:
they decide which pages are embedded at all (global to the DB), unlike the
root-level namespace keys, which filter query results per instance. Changing
them takes effect only after `logseq-sync --rebuild`.

Supported embedder providers are "ollama", "openai", and
"openai-compatible". Hosted providers may also use "api_key" and "dimensions"
inside the embedder block.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("mcp-logseq.config")


@dataclass
class EmbedderConfig:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    dimensions: int | None = None


@dataclass
class VectorConfig:
    enabled: bool
    db_path: str
    embedder: EmbedderConfig
    graph_path: str                         # logseq_graph_path from root config
    include_journals: bool = True
    exclude_tags: list[str] = field(default_factory=list)
    include_namespaces: list[str] = field(default_factory=list)
    exclude_namespaces: list[str] = field(default_factory=list)
    min_chunk_length: int = 50
    watch_debounce_ms: int = 5000


def read_config_file() -> dict | None:
    """Read and parse the JSON file pointed to by LOGSEQ_CONFIG_FILE.

    Single choke point for config-file IO: returns None if the env var is not
    set, the file is missing, or it cannot be parsed. Never raises — logs
    warnings on issues.
    """
    config_path = os.getenv("LOGSEQ_CONFIG_FILE")
    if not config_path:
        return None

    config_path = os.path.expanduser(config_path)
    if not os.path.exists(config_path):
        logger.warning(f"LOGSEQ_CONFIG_FILE set but file not found: {config_path}")
        return None

    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to parse config file {config_path}: {e}")
        return None


def load_vector_config() -> VectorConfig | None:
    """
    Load vector config from LOGSEQ_CONFIG_FILE.
    Returns None if env var is not set, file is missing, or vector.enabled is not true.
    Never raises — logs warnings on issues.
    """
    raw = read_config_file()
    if raw is None:
        return None

    vector_raw = raw.get("vector")
    if not isinstance(vector_raw, dict) or not vector_raw.get("enabled"):
        return None

    graph_path = raw.get("logseq_graph_path", "")
    if not graph_path:
        logger.warning("Config file missing 'logseq_graph_path' — required for vector sync")
        return None

    embedder_raw = vector_raw.get("embedder", {})
    if not isinstance(embedder_raw, dict):
        logger.warning("Vector 'embedder' configuration must be an object")
        return None
    provider = str(embedder_raw.get("provider", "ollama")).strip().lower()
    supported_providers = {"ollama", "openai", "openai-compatible"}
    if provider not in supported_providers:
        supported = ", ".join(sorted(supported_providers))
        logger.warning(
            f"Unsupported embedder provider '{provider}' — supported providers: {supported}"
        )
        return None

    default_models = {
        "ollama": "nomic-embed-text",
        "openai": "text-embedding-3-small",
        "openai-compatible": "",
    }
    default_base_urls = {
        "ollama": "http://localhost:11434",
        "openai": "https://api.openai.com/v1",
        "openai-compatible": "",
    }
    model_raw = embedder_raw.get("model")
    base_url_raw = embedder_raw.get("base_url")
    model = str(
        default_models[provider] if model_raw is None else model_raw
    ).strip()
    base_url = str(
        default_base_urls[provider] if base_url_raw is None else base_url_raw
    ).strip()
    api_key_raw = embedder_raw.get("api_key")
    api_key = str(api_key_raw).strip() if api_key_raw is not None else None
    dimensions = embedder_raw.get("dimensions")

    if not model:
        logger.warning(f"Embedder provider '{provider}' requires 'model'")
        return None
    if not base_url:
        logger.warning(f"Embedder provider '{provider}' requires 'base_url'")
        return None
    if provider == "openai" and not api_key:
        logger.warning("Embedder provider 'openai' requires 'api_key'")
        return None
    if dimensions is not None and (
        isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0
    ):
        logger.warning("Embedder 'dimensions' must be a positive integer")
        return None

    embedder = EmbedderConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        dimensions=dimensions,
    )

    db_path = os.path.expanduser(vector_raw.get("db_path", "~/.logseq-vector"))

    return VectorConfig(
        enabled=True,
        db_path=db_path,
        embedder=embedder,
        graph_path=os.path.expanduser(graph_path),
        include_journals=vector_raw.get("include_journals", True),
        exclude_tags=vector_raw.get("exclude_tags", []),
        include_namespaces=vector_raw.get("include_namespaces", []),
        exclude_namespaces=vector_raw.get("exclude_namespaces", []),
        min_chunk_length=vector_raw.get("min_chunk_length", 50),
        watch_debounce_ms=vector_raw.get("watch_debounce_ms", 5000),
    )


def csv_config_value(raw: dict | None, env_var: str, config_key: str) -> list[str]:
    """Resolve a comma/list config value from an env var or a parsed config dict.

    Priority: env var > config file root key > [] (no value).
    env var: comma-separated string. config file: list or comma-separated string.
    Strips whitespace and drops empties. Never raises.

    ``raw`` is the already-parsed config file (``read_config_file()``), so
    callers resolving several keys parse the file only once.
    """
    env_val = os.getenv(env_var, "").strip()
    if env_val:
        items = [t.strip() for t in env_val.split(",") if t.strip()]
        if items:
            logger.info(f"Loaded {len(items)} entries from {env_var}")
            return items

    if raw is None:
        return []

    raw_val = raw.get(config_key, [])
    if isinstance(raw_val, list):
        items = [str(t).strip() for t in raw_val if str(t).strip()]
    elif isinstance(raw_val, str):
        items = [t.strip() for t in raw_val.split(",") if t.strip()]
    else:
        items = []
    if items:
        logger.info(f"Loaded {len(items)} entries for '{config_key}' from config file root")
    return items


def load_exclude_tags() -> list[str]:
    """Load top-level exclude_tags. Priority: env var > config file > []."""
    return csv_config_value(read_config_file(), "LOGSEQ_EXCLUDE_TAGS", "exclude_tags")


def load_include_namespaces() -> list[str]:
    """Load allow-list namespaces. Priority: env var > config file > []."""
    return csv_config_value(read_config_file(), "LOGSEQ_INCLUDE_NAMESPACES", "include_namespaces")


def load_exclude_namespaces() -> list[str]:
    """Load deny-list namespaces. Priority: env var > config file > []."""
    return csv_config_value(read_config_file(), "LOGSEQ_EXCLUDE_NAMESPACES", "exclude_namespaces")
