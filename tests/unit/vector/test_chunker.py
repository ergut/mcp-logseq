from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_logseq.config import EmbedderConfig, VectorConfig
from mcp_logseq.vector.chunker import (
    _clean_for_embedding,
    _detect_journal_date,
    _flatten_block,
    chunk_file,
)


def _make_config(**kwargs) -> VectorConfig:
    defaults = dict(
        enabled=True,
        db_path="/tmp/test-db",
        embedder=EmbedderConfig(provider="ollama", model="nomic-embed-text"),
        graph_path="/tmp/graph",
        include_journals=True,
        exclude_tags=[],
        min_chunk_length=10,
        watch_debounce_ms=5000,
    )
    defaults.update(kwargs)
    return VectorConfig(**defaults)


# --- Unit tests for helpers ---

def test_detect_journal_date_underscore():
    assert _detect_journal_date("2024_03_15") == "2024-03-15"


def test_detect_journal_date_hyphen():
    assert _detect_journal_date("2024-03-15") == "2024-03-15"


def test_detect_journal_date_non_journal():
    assert _detect_journal_date("My Page") is None
    assert _detect_journal_date("project_notes") is None


def test_clean_removes_block_refs():
    text = "See ((a1b2c3d4-e5f6-7890-abcd-ef1234567890)) for details"
    result = _clean_for_embedding(text)
    assert "((" not in result
    assert "))" not in result


def test_clean_expands_page_links():
    text = "Check out [[Project Alpha]] and [[Meeting Notes]]"
    result = _clean_for_embedding(text)
    assert "Project Alpha" in result
    assert "Meeting Notes" in result
    assert "[[" not in result


def test_clean_removes_properties():
    text = "Some content\ntags:: work, personal\nAnother line"
    result = _clean_for_embedding(text)
    assert "tags::" not in result
    assert "Some content" in result


def test_clean_removes_bullet_markers():
    text = "- This is a bullet point"
    result = _clean_for_embedding(text)
    assert not result.startswith("-")
    assert "This is a bullet point" in result


def test_clean_normalizes_whitespace():
    text = "  lots   of   space  "
    result = _clean_for_embedding(text)
    assert "  " not in result
    assert result.strip() == result


# --- Integration tests with actual files ---

def test_chunk_file_basic(tmp_path):
    md_file = tmp_path / "My Page.md"
    md_file.write_text("- First block with enough content here\n- Second block also has content\n")
    config = _make_config(graph_path=str(tmp_path))

    chunks = chunk_file(md_file, config)
    assert len(chunks) >= 1
    assert all(c.page == "My Page" for c in chunks)
    assert all(c.vector is None for c in chunks)  # not embedded yet


def test_chunk_file_journal_page(tmp_path):
    md_file = tmp_path / "2024_03_15.md"
    md_file.write_text("- Went to the gym today and it was great\n")
    config = _make_config(graph_path=str(tmp_path))

    chunks = chunk_file(md_file, config)
    assert len(chunks) >= 1
    assert chunks[0].date == "2024-03-15"


def test_chunk_file_skips_short_chunks(tmp_path):
    md_file = tmp_path / "Short.md"
    md_file.write_text("- Hi\n- Also brief\n")
    config = _make_config(graph_path=str(tmp_path), min_chunk_length=50)

    chunks = chunk_file(md_file, config)
    assert len(chunks) == 0


def test_chunk_file_exclude_tags_filters_page(tmp_path):
    md_file = tmp_path / "Private Page.md"
    md_file.write_text("tags:: private\n\n- This should be excluded from indexing\n")
    config = _make_config(graph_path=str(tmp_path), exclude_tags=["private"])

    chunks = chunk_file(md_file, config)
    assert chunks == []


def test_chunk_file_skips_journals_when_disabled(tmp_path):
    md_file = tmp_path / "2024_03_15.md"
    md_file.write_text("- Journal content with enough characters here\n")
    config = _make_config(graph_path=str(tmp_path), include_journals=False)

    chunks = chunk_file(md_file, config)
    assert chunks == []


def test_chunk_file_chunk_ids(tmp_path):
    md_file = tmp_path / "Test Page.md"
    md_file.write_text(
        "- First block with enough text content for chunking\n"
        "- Second block with enough text content for chunking\n"
    )
    config = _make_config(graph_path=str(tmp_path))

    chunks = chunk_file(md_file, config)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))  # all unique
    assert all(c.id.startswith("Test Page::") for c in chunks)


def test_chunk_file_frontmatter_properties(tmp_path):
    md_file = tmp_path / "Note With Props.md"
    md_file.write_text(
        "---\ntitle: My Custom Title\ntags: [work, research]\n---\n\n"
        "- Some content with enough characters to pass the filter\n"
    )
    config = _make_config(graph_path=str(tmp_path))

    chunks = chunk_file(md_file, config)
    assert len(chunks) >= 1
    assert chunks[0].page == "My Custom Title"
    assert "work" in chunks[0].tags or "research" in chunks[0].tags


def test_chunk_file_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.md"
    config = _make_config(graph_path=str(tmp_path))

    chunks = chunk_file(missing, config)
    assert chunks == []
