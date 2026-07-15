"""Tool handlers for the MCP LogSeq server.

This package was split out of a single ``tools.py`` module (architecture
review item A3). The public surface is unchanged: every handler class and
helper that used to live in ``mcp_logseq.tools`` is re-exported here, so
``from mcp_logseq.tools import ...`` and ``patch("mcp_logseq.tools.<name>")``
continue to work exactly as before.

``logseq``, ``_make_api`` and ``_get_db_mode`` are re-exported so existing
``patch()`` targets keep resolving against this package; submodules reach
them at call time via ``import mcp_logseq.tools as _t`` (see ``base.py``).
"""

# Re-exported so `patch("mcp_logseq.tools.logseq.LogSeq")` keeps working.
from .. import logseq

from ..access import (
    AccessDenied,
    extract_tags as _extract_tags,
    is_page_excluded as _is_page_excluded,
    is_page_blocked as _is_page_blocked,
)
from ..namespace import is_namespace_blocked as _is_namespace_blocked

from .base import (
    ToolHandler,
    _make_api,
    _get_db_mode,
    _UUID_REF_PATTERN,
    _collect_block_uuids,
    _resolve_block_refs,
    logger,
)

from .pages import (
    CreatePageToolHandler,
    ListPagesToolHandler,
    GetPageContentToolHandler,
    DeletePageToolHandler,
    UpdatePageToolHandler,
    FindPagesByPropertyToolHandler,
    RenamePageToolHandler,
    GetPageBacklinksToolHandler,
)
from .blocks import (
    DeleteBlockToolHandler,
    UpdateBlockToolHandler,
    GetBlockToolHandler,
    InsertNestedBlockToolHandler,
    SetBlockPropertiesToolHandler,
)
from .search import (
    SearchToolHandler,
    QueryToolHandler,
)
from .namespace import (
    GetPagesFromNamespaceToolHandler,
    GetPagesTreeFromNamespaceToolHandler,
)

__all__ = [
    "ToolHandler",
    "AccessDenied",
    "CreatePageToolHandler",
    "ListPagesToolHandler",
    "GetPageContentToolHandler",
    "DeletePageToolHandler",
    "UpdatePageToolHandler",
    "DeleteBlockToolHandler",
    "UpdateBlockToolHandler",
    "GetBlockToolHandler",
    "SearchToolHandler",
    "QueryToolHandler",
    "FindPagesByPropertyToolHandler",
    "GetPagesFromNamespaceToolHandler",
    "GetPagesTreeFromNamespaceToolHandler",
    "RenamePageToolHandler",
    "GetPageBacklinksToolHandler",
    "InsertNestedBlockToolHandler",
    "SetBlockPropertiesToolHandler",
]
