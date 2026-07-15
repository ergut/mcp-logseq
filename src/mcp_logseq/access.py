"""Access control (ACL) configuration and enforcement.

Owns the resolved exclude-tag / namespace lists and every predicate and
enforcement helper built on them. Shared by the query-time tool layer
(``tools.py``) and the vector search layer (``vector/index.py``), so neither
has to reach into the other's internals.

Like ``settings.py``, loading is lazy: importing this module has no side
effects. The ACL lists are read from the environment / config file on first
use via ``get_access_config()`` and cached for the life of the process.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field

from .config import csv_config_value, read_config_file
from .namespace import is_namespace_blocked

logger = logging.getLogger("mcp-logseq")


@dataclass(frozen=True)
class AccessConfig:
    """Resolved ACL lists (exclude tags plus namespace allow/deny lists)."""

    exclude_tags: list[str] = field(default_factory=list)
    include_namespaces: list[str] = field(default_factory=list)
    exclude_namespaces: list[str] = field(default_factory=list)

    @property
    def has_rules(self) -> bool:
        return bool(
            self.exclude_tags or self.include_namespaces or self.exclude_namespaces
        )


def load_access_config() -> AccessConfig:
    """Resolve the ACL lists from env vars / the config file.

    Parses the config file once for all three lists (env vars take priority
    per list). Never raises.
    """
    raw = read_config_file()
    return AccessConfig(
        exclude_tags=csv_config_value(raw, "LOGSEQ_EXCLUDE_TAGS", "exclude_tags"),
        include_namespaces=csv_config_value(
            raw, "LOGSEQ_INCLUDE_NAMESPACES", "include_namespaces"
        ),
        exclude_namespaces=csv_config_value(
            raw, "LOGSEQ_EXCLUDE_NAMESPACES", "exclude_namespaces"
        ),
    )


@functools.cache
def get_access_config() -> AccessConfig:
    """Return the process-wide ``AccessConfig``, loading it on first use.

    Cached for the life of the process; call ``get_access_config.cache_clear()``
    (tests) to force a reload from the environment.
    """
    return load_access_config()


class AccessDenied(RuntimeError):
    """Raised when a tool is blocked from accessing a restricted page."""


def extract_tags(properties: dict) -> list[str]:
    """Extract tags from a Logseq properties dict (list or comma-string form)."""
    raw = properties.get("tags", [])
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return []


def is_page_excluded(page: dict, exclude_tags: list[str]) -> bool:
    """Return True if the page has any tag in exclude_tags."""
    if not exclude_tags:
        return False
    props = page.get("properties") or {}
    return any(t in exclude_tags for t in extract_tags(props))


def is_page_blocked(page: dict | None, page_name: str) -> bool:
    """Combined tag OR namespace block check (used for result filtering)."""
    acl = get_access_config()
    if page and is_page_excluded(page, acl.exclude_tags):
        return True
    return is_namespace_blocked(
        page_name, acl.include_namespaces, acl.exclude_namespaces
    )


def enforce_namespace_access(page_name: str) -> None:
    """Raise AccessDenied if page_name is blocked by namespace rules.

    Name-based only (no tag check — that needs fetched page properties).
    """
    acl = get_access_config()
    if is_namespace_blocked(page_name, acl.include_namespaces, acl.exclude_namespaces):
        raise AccessDenied(
            f"Access denied: page '{page_name}' is restricted "
            f"and cannot be accessed by this assistant."
        )


def enforce_block_namespace_access(api, block_uuid: str) -> None:
    """Resolve a block's owning page and enforce namespace rules.

    Fail-closed: when namespace rules are configured but the page cannot be
    resolved, access is denied. When no namespace rules exist, this is a no-op.
    """
    acl = get_access_config()
    if not acl.include_namespaces and not acl.exclude_namespaces:
        return
    page_name = api.get_block_page_name(block_uuid)
    if page_name is None:
        raise AccessDenied(
            f"Access denied: cannot verify the namespace of block '{block_uuid}'."
        )
    enforce_namespace_access(page_name)


def enforce_page_tag_access(api, page_name: str) -> None:
    """Raise AccessDenied if an EXISTING page carries an excluded tag.

    Complements the name-based namespace check on write handlers: namespace
    rules can be evaluated from the name alone, but tag exclusion requires the
    page's properties, so this fetches the page. A no-op when no exclude tags
    are configured.

    Two cases are NOT excluded — but only the first is also a quiet pass:
    - ``get_page_content`` returns None/empty: the page does not exist (or has
      no properties) and therefore carries no tags. Treated as NOT excluded so
      ``update_page`` keeps working for brand-new pages.
    - ``get_page_content`` RAISES: with exclude tags configured we cannot verify
      the page's tags, so we must NOT silently proceed with the write. The error
      is allowed to propagate (no try/except) so the calling write handler
      aborts the mutation via its normal error path (fail-closed). It is not an
      AccessDenied, so it isn't mislabeled — it just isn't swallowed.
    """
    acl = get_access_config()
    if not acl.exclude_tags:
        return
    # No try/except by design: when exclude tags are configured, a fetch error
    # must abort the write rather than fail open. A non-existent page returns
    # None and falls through as not-excluded.
    result = api.get_page_content(page_name)
    if result and is_page_excluded(result.get("page", {}), acl.exclude_tags):
        raise AccessDenied(
            f"Access denied: page '{page_name}' is restricted "
            f"and cannot be accessed by this assistant."
        )


def enforce_block_tag_access(api, block_uuid: str) -> None:
    """Resolve a block's owning page and enforce tag exclusion on it.

    A no-op when no exclude tags are configured. When tags ARE configured but
    the owning page cannot be resolved, access is denied (fail-closed), mirroring
    ``enforce_block_namespace_access``.
    """
    acl = get_access_config()
    if not acl.exclude_tags:
        return
    page_name = api.get_block_page_name(block_uuid)
    if page_name is None:
        raise AccessDenied(
            f"Access denied: cannot verify the owning page of block '{block_uuid}'."
        )
    enforce_page_tag_access(api, page_name)
