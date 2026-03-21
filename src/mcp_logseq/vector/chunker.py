"""
Chunker for Logseq markdown files.

Builds on the existing parser.py to get a structured block tree,
then converts each top-level block (+ its children) into a LogseqChunk.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from mcp_logseq.config import VectorConfig
from mcp_logseq.parser import BlockNode, parse_content
from mcp_logseq.vector.types import LogseqChunk

logger = logging.getLogger("mcp-logseq.vector.chunker")

# Matches YYYY_MM_DD.md or YYYY-MM-DD.md (Logseq journal filenames)
_JOURNAL_PATTERN = re.compile(r"^(\d{4})[_-](\d{2})[_-](\d{2})$")

# Cleaning patterns for embedding text
_BLOCK_REF = re.compile(r"\(\([a-f0-9-]{36}\)\)")          # ((uuid))
_PAGE_LINK = re.compile(r"\[\[([^\]]+)\]\]")               # [[Page Name]]
_PROPERTY_LINE = re.compile(r"^\s*[\w-]+::\s*.+$", re.M)  # key:: value
_INLINE_PROPERTY = re.compile(r"^([\w-]+)::\s*(.+)$")     # single key:: value line
_BULLET_MARKER = re.compile(r"^[-*+]\s+")                  # leading bullet
_EXTRA_WS = re.compile(r"\s+")                             # whitespace normalization


def _detect_journal_date(stem: str) -> str | None:
    """Return YYYY-MM-DD if filename is a journal page, else None."""
    m = _JOURNAL_PATTERN.match(stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _flatten_block(node: BlockNode) -> str:
    """Recursively join a block and all its children into a single string."""
    parts = [node.content]
    for child in node.children:
        parts.append(_flatten_block(child))
    return "\n".join(p for p in parts if p.strip())


def _clean_for_embedding(text: str) -> str:
    """Strip Logseq-specific syntax to produce clean text for embedding."""
    text = _BLOCK_REF.sub("", text)
    text = _PAGE_LINK.sub(r"\1", text)
    text = _PROPERTY_LINE.sub("", text)
    text = _BULLET_MARKER.sub("", text)
    text = _EXTRA_WS.sub(" ", text)
    return text.strip()


def _extract_inline_properties(blocks: list[BlockNode]) -> dict:
    """
    Extract Logseq inline page properties (key:: value) from blocks.

    In Logseq, page properties are written as consecutive `key:: value` lines
    at the top of the file body. The parser groups these into a single block
    whose content is all those key:: value lines joined by newlines.
    We scan early blocks for this pattern and merge into a properties dict.
    """
    props: dict = {}
    for block in blocks:
        # A "property block" is one where every non-empty line is a key:: value line
        lines = [l.strip() for l in block.content.splitlines() if l.strip()]
        if not lines:
            continue
        all_props = all(_INLINE_PROPERTY.match(l) for l in lines)
        if all_props:
            for line in lines:
                m = _INLINE_PROPERTY.match(line)
                if m:
                    key, value = m.group(1).strip(), m.group(2).strip()
                    props[key] = value
        else:
            # Stop at first non-property block (properties are always at the top)
            break
    return props


def _page_title_from_file(file_path: Path, properties: dict) -> str:
    """Derive page title from title:: property or filename."""
    if "title" in properties:
        return str(properties["title"])
    # URL-decode % encoding Logseq uses in filenames (e.g. %2F for /)
    stem = file_path.stem
    try:
        from urllib.parse import unquote
        stem = unquote(stem)
    except Exception:
        pass
    return stem.replace("___", "/")  # Logseq namespace separator


def chunk_file(file_path: Path, config: VectorConfig) -> list[LogseqChunk]:
    """
    Parse a Logseq markdown file and return a list of LogseqChunk objects.

    Each top-level block (plus all its children) becomes one chunk.
    Page-level properties are attached to every chunk from that page.
    Returns an empty list if the page is filtered by tag rules.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Cannot read {file_path}: {e}")
        return []

    parsed = parse_content(text)
    # Merge frontmatter YAML props with Logseq inline key:: value props
    # Frontmatter takes precedence if both define the same key
    inline_props = _extract_inline_properties(parsed.blocks)
    props = {**inline_props, **parsed.properties}

    page_title = _page_title_from_file(file_path, props)

    # Tag filtering — get tags from properties (may be list or comma string)
    raw_tags = props.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    # Apply exclude_tags filter
    if config.exclude_tags and any(t in config.exclude_tags for t in tags):
        logger.debug(f"Skipping {page_title}: excluded by tag filter")
        return []

    # Journal date detection
    date: str | None = _detect_journal_date(file_path.stem)
    if date is None:
        raw_date = props.get("date")
        if raw_date:
            date = str(raw_date)

    # Skip journal pages if include_journals is False
    if not config.include_journals and date is not None and _JOURNAL_PATTERN.match(file_path.stem):
        logger.debug(f"Skipping journal page: {page_title}")
        return []

    # Serialize all page properties (excluding tags/date which are separate fields)
    serializable_props = {k: v for k, v in props.items()}
    properties_json = json.dumps(serializable_props, default=str)

    # Identify which blocks are pure property blocks (metadata, not content)
    property_block_indices: set[int] = set()
    for i, block in enumerate(parsed.blocks):
        lines = [l.strip() for l in block.content.splitlines() if l.strip()]
        if lines and all(_INLINE_PROPERTY.match(l) for l in lines):
            property_block_indices.add(i)
        else:
            break  # properties are always at the top

    chunks: list[LogseqChunk] = []
    for block_index, block in enumerate(parsed.blocks):
        if block_index in property_block_indices:
            continue  # skip pure property blocks — they're metadata
        raw = _flatten_block(block)
        text_clean = _clean_for_embedding(raw)

        if len(text_clean) < config.min_chunk_length:
            continue

        chunk_id = f"{page_title}::{block_index}"
        chunks.append(LogseqChunk(
            id=chunk_id,
            page=page_title,
            text=text_clean,
            raw=raw,
            tags=tags,
            date=date,
            properties=properties_json,
            block_index=block_index,
        ))

    return chunks
