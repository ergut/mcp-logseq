"""Shared building blocks for the tool handlers.

Holds the ``ToolHandler`` base class, the API factory, and the DB-mode
block-reference helpers. Runtime config helpers (``_make_api``,
``_get_db_mode``) live here but are also re-exported from the package
``__init__`` so that ``patch("mcp_logseq.tools._make_api")`` — used
throughout the test suite — keeps working; submodules call them via the
package namespace (``_t._make_api()``) for the same reason.
"""

import re
import logging

from .. import logseq
from ..settings import get_settings
from mcp.types import Tool, TextContent

logger = logging.getLogger("mcp-logseq")


def _get_db_mode() -> bool:
    return get_settings().db_mode


def _make_api() -> logseq.LogSeq:
    settings = get_settings()
    return logseq.LogSeq(
        api_key=settings.api_key,
        protocol=settings.protocol,
        host=settings.host,
        port=settings.port,
        verify_ssl=settings.verify_ssl,
        timeout=settings.timeout,
        db_mode=settings.db_mode,
    )


# Regex matching [[uuid]] references in DB-mode block content
_UUID_REF_PATTERN = re.compile(r"\[\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]\]")


def _collect_block_uuids(blocks: list[dict]) -> set[str]:
    """Recursively collect all page-reference UUIDs from block content strings."""
    uuids: set[str] = set()
    for block in blocks:
        content = block.get("content", "")
        uuids.update(_UUID_REF_PATTERN.findall(content))
        children = block.get("children", [])
        if children:
            uuids.update(_collect_block_uuids(children))
    return uuids


def _resolve_block_refs(content: str, uuid_map: dict[str, str]) -> str:
    """Replace [[uuid]] patterns in content with [[Page Name]] using a pre-resolved map."""
    def _replace(match: re.Match) -> str:
        uuid = match.group(1)
        name = uuid_map.get(uuid)
        if name:
            return f"[[{name}]]"
        return match.group(0)  # Keep original if not resolved

    return _UUID_REF_PATTERN.sub(_replace, content)


class ToolHandler:
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> list[TextContent]:
        raise NotImplementedError()
