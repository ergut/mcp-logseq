"""Pure, side-effect-free namespace matching.

Shared by the query-time ACL layer (``tools.py``) and the index-time vector
indexer (``vector/chunker.py``). Kept dependency-free so the sync writer, which
runs without ``LOGSEQ_API_TOKEN``, can import it without triggering ``tools.py``'s
import-time environment checks.
"""

from __future__ import annotations


def namespace_matches(page_name: str, ns: str) -> bool:
    """Segment-based, case-insensitive namespace match.

    'work' matches 'work' and 'work/...'; it does NOT match 'workshop'.
    """
    p = page_name.lower()
    n = ns.lower().rstrip("/")
    if not n:
        return False
    return p == n or p.startswith(n + "/")


def is_namespace_blocked(page_name: str, include: list[str], exclude: list[str]) -> bool:
    """Apply namespace rules. Exclude wins; include is a strict allow-list."""
    if any(namespace_matches(page_name, n) for n in exclude):
        return True
    if include and not any(namespace_matches(page_name, n) for n in include):
        return True
    return False
