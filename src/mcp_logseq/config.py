"""
Config file loading for mcp-logseq.

Set LOGSEQ_CONFIG_FILE to a path pointing to a JSON config file.
If not set, or if vector.enabled is false/missing, vector tools are not loaded.

Example config.json:
{
  "logseq_graph_path": "/path/to/logseq/pages",
  "exclude_tags": ["private", "secret"],
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
    "min_chunk_length": 50,
    "watch_debounce_ms": 5000
  }
}
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
    base_url: str = "http://localhost:11434"


@dataclass
class VectorConfig:
    enabled: bool
    db_path: str
    embedder: EmbedderConfig
    graph_path: str                         # logseq_graph_path from root config
    include_journals: bool = True
    exclude_tags: list[str] = field(default_factory=list)
    min_chunk_length: int = 50
    watch_debounce_ms: int = 5000


def load_vector_config() -> VectorConfig | None:
    """
    Load vector config from LOGSEQ_CONFIG_FILE.
    Returns None if env var is not set, file is missing, or vector.enabled is not true.
    Never raises — logs warnings on issues.
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
            raw = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to parse config file {config_path}: {e}")
        return None

    vector_raw = raw.get("vector")
    if not vector_raw or not vector_raw.get("enabled"):
        return None

    graph_path = raw.get("logseq_graph_path", "")
    if not graph_path:
        logger.warning("Config file missing 'logseq_graph_path' — required for vector sync")
        return None

    embedder_raw = vector_raw.get("embedder", {})
    provider = embedder_raw.get("provider", "ollama")
    if provider != "ollama":
        logger.warning(f"Unsupported embedder provider '{provider}' — only 'ollama' is supported")
        return None

    embedder = EmbedderConfig(
        provider=provider,
        model=embedder_raw.get("model", "nomic-embed-text"),
        base_url=embedder_raw.get("base_url", "http://localhost:11434"),
    )

    db_path = os.path.expanduser(vector_raw.get("db_path", "~/.logseq-vector"))

    return VectorConfig(
        enabled=True,
        db_path=db_path,
        embedder=embedder,
        graph_path=os.path.expanduser(graph_path),
        include_journals=vector_raw.get("include_journals", True),
        exclude_tags=vector_raw.get("exclude_tags", []),
        min_chunk_length=vector_raw.get("min_chunk_length", 50),
        watch_debounce_ms=vector_raw.get("watch_debounce_ms", 5000),
    )


def load_exclude_tags() -> list[str]:
    """
    Load top-level exclude_tags from LOGSEQ_EXCLUDE_TAGS env var or config file root.
    Priority: env var > config file > [] (no filtering).
    Never raises.
    """
    env_val = os.getenv("LOGSEQ_EXCLUDE_TAGS", "").strip()
    if env_val:
        tags = [t.strip() for t in env_val.split(",") if t.strip()]
        if tags:
            logger.info(f"Loaded {len(tags)} exclude_tags from LOGSEQ_EXCLUDE_TAGS")
            return tags

    config_path = os.getenv("LOGSEQ_CONFIG_FILE")
    if not config_path:
        return []
    config_path = os.path.expanduser(config_path)
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path) as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to parse config file for exclude_tags {config_path}: {e}")
        return []

    raw_tags = raw.get("exclude_tags", [])
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []
    if tags:
        logger.info(f"Loaded {len(tags)} exclude_tags from config file root")
    return tags
