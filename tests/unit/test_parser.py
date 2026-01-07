"""
Tests for the markdown to Logseq block parser.
"""

import pytest
from mcp_logseq.parser import (
    parse_frontmatter,
    parse_markdown_to_blocks,
    parse_content,
    blocks_to_batch_format,
    BlockNode,
    ParsedContent,
)


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_valid_yaml_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = """---
tags: [project, active]
priority: high
---

# Content starts here
"""
        properties, remaining = parse_frontmatter(content)

        assert properties == {"tags": ["project", "active"], "priority": "high"}
        assert "# Content starts here" in remaining
        assert "---" not in remaining

    def test_no_frontmatter(self):
        """Test content without frontmatter."""
        content = "# Just a heading\n\nSome content."

        properties, remaining = parse_frontmatter(content)

        assert properties == {}
        assert remaining == content

    def test_empty_frontmatter(self):
        """Test empty frontmatter block."""
        content = """---
---

# Content
"""
        properties, remaining = parse_frontmatter(content)

        assert properties == {}
        assert "# Content" in remaining

    def test_frontmatter_with_nested_objects(self):
        """Test frontmatter with nested YAML structures."""
        content = """---
metadata:
  author: John
  date: 2025-01-06
tags:
  - project
  - important
---

Content here.
"""
        properties, remaining = parse_frontmatter(content)

        assert properties["metadata"]["author"] == "John"
        # Date should be converted to ISO string for JSON serialization
        assert properties["metadata"]["date"] == "2025-01-06"
        assert properties["tags"] == ["project", "important"]

    def test_frontmatter_date_serialization(self):
        """Test that date and datetime values are converted to ISO strings."""
        import json

        content = """---
due-date: 2026-01-15
created: 2026-01-06T10:30:00
tags: [test]
---

Content here.
"""
        properties, remaining = parse_frontmatter(content)

        # Dates should be ISO strings, not datetime objects
        assert properties["due-date"] == "2026-01-15"
        assert properties["created"] == "2026-01-06T10:30:00"

        # Should be JSON serializable
        json_str = json.dumps(properties)
        assert "2026-01-15" in json_str
        assert "2026-01-06T10:30:00" in json_str

    def test_malformed_yaml_returns_empty(self):
        """Test that malformed YAML returns empty properties."""
        content = """---
this is: not: valid: yaml
  - broken indentation
---

Content here.
"""
        properties, remaining = parse_frontmatter(content)

        # Should return empty dict and preserve content
        assert properties == {}

    def test_frontmatter_only_at_start(self):
        """Test that --- in content is not treated as frontmatter end."""
        content = """---
key: value
---

Some content

---

This should remain as content.
"""
        properties, remaining = parse_frontmatter(content)

        assert properties == {"key": "value"}
        assert "---" in remaining  # The horizontal rule should remain
        assert "This should remain as content" in remaining


class TestParseMarkdownHeadings:
    """Tests for heading parsing and hierarchy."""

    def test_single_h1(self):
        """Test parsing a single H1 heading."""
        content = "# My Title"
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "# My Title"
        assert blocks[0].level == 1

    def test_heading_hierarchy(self):
        """Test that headings create proper hierarchy."""
        content = """# H1 Title

## H2 Section

### H3 Subsection
"""
        blocks = parse_markdown_to_blocks(content)

        # Should have one root block (H1) with children
        assert len(blocks) == 1
        assert blocks[0].content == "# H1 Title"

        # H2 should be child of H1
        assert len(blocks[0].children) == 1
        h2_block = blocks[0].children[0]
        assert h2_block.content == "## H2 Section"

        # H3 should be child of H2
        assert len(h2_block.children) == 1
        assert h2_block.children[0].content == "### H3 Subsection"

    def test_heading_with_content_underneath(self):
        """Test that content under headings becomes children."""
        content = """# Title

This is intro content.

## Section

Section content here.
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "# Title"

        # Should have paragraph and H2 as children
        children = blocks[0].children
        assert len(children) == 2
        assert children[0].content == "This is intro content."
        assert children[1].content == "## Section"

    def test_multiple_same_level_headings(self):
        """Test multiple H1 headings create siblings."""
        content = """# First H1

Content 1

# Second H1

Content 2
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].content == "# First H1"
        assert blocks[1].content == "# Second H1"


class TestParseMarkdownLists:
    """Tests for list parsing with nesting.

    Note: List markers (-, *, +, 1., etc.) are stripped from content
    because Logseq blocks are already rendered as bullets. Including
    the marker would create redundant bullet points.
    """

    def test_simple_bullet_list(self):
        """Test simple bullet list - markers should be stripped."""
        content = """- Item 1
- Item 2
- Item 3
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 3
        # Markers stripped - Logseq renders each block as a bullet already
        assert blocks[0].content == "Item 1"
        assert blocks[1].content == "Item 2"
        assert blocks[2].content == "Item 3"

    def test_nested_bullet_list(self):
        """Test nested bullet list - markers stripped, hierarchy preserved."""
        content = """- Parent item
  - Child item 1
  - Child item 2
    - Grandchild
- Another parent
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2

        # First parent with children - markers stripped
        assert blocks[0].content == "Parent item"
        assert len(blocks[0].children) == 2
        assert blocks[0].children[0].content == "Child item 1"
        assert blocks[0].children[1].content == "Child item 2"

        # Grandchild
        assert len(blocks[0].children[1].children) == 1
        assert blocks[0].children[1].children[0].content == "Grandchild"

        # Second parent
        assert blocks[1].content == "Another parent"

    def test_numbered_list(self):
        """Test numbered list - numbers stripped."""
        content = """1. First item
2. Second item
3. Third item
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 3
        # Numbers stripped - Logseq handles numbering via block properties if needed
        assert blocks[0].content == "First item"
        assert blocks[1].content == "Second item"

    def test_checkbox_list(self):
        """Test checkbox/todo list - converts to Logseq TODO/DONE format."""
        content = """- [ ] Unchecked task
- [x] Checked task
- [X] Also checked
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 3
        # Checkboxes convert to Logseq TODO/DONE syntax
        assert blocks[0].content == "TODO Unchecked task"
        assert blocks[1].content == "DONE Checked task"
        assert blocks[2].content == "DONE Also checked"

    def test_mixed_list_types(self):
        """Test mixing bullet and numbered lists - all markers stripped."""
        content = """- Bullet item
1. Numbered item
- Another bullet
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 3
        assert blocks[0].content == "Bullet item"
        assert blocks[1].content == "Numbered item"
        assert blocks[2].content == "Another bullet"


class TestParseMarkdownCodeBlocks:
    """Tests for code block parsing."""

    def test_fenced_code_block(self):
        """Test fenced code block."""
        content = """```
def hello():
    print("world")
```
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert "```" in blocks[0].content
        assert "def hello():" in blocks[0].content
        assert 'print("world")' in blocks[0].content

    def test_fenced_code_with_language(self):
        """Test fenced code block with language specification."""
        content = """```python
import os
print(os.getcwd())
```
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert "```python" in blocks[0].content
        assert "import os" in blocks[0].content

    def test_code_block_under_heading(self):
        """Test code block as child of heading."""
        content = """# Code Example

```javascript
console.log("hello");
```
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "# Code Example"
        assert len(blocks[0].children) == 1
        assert "```javascript" in blocks[0].children[0].content


class TestParseMarkdownOther:
    """Tests for other markdown elements."""

    def test_blockquote(self):
        """Test blockquote parsing - contiguous lines should be single block."""
        content = """> This is a quote
> Continued quote
"""
        blocks = parse_markdown_to_blocks(content)

        # Contiguous blockquote lines become a single block
        assert len(blocks) == 1
        assert blocks[0].content == "> This is a quote\n> Continued quote"

    def test_blockquote_separate_paragraphs(self):
        """Test separate blockquotes (separated by empty line) become separate blocks."""
        content = """> First quote

> Second quote
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].content == "> First quote"
        assert blocks[1].content == "> Second quote"

    def test_blockquote_with_empty_quote_line(self):
        """Test blockquote with empty > line stays as single block."""
        content = """> Line 1
> Line 2
>
> Line 3
"""
        blocks = parse_markdown_to_blocks(content)

        # All contiguous > lines (including empty >) are one block
        assert len(blocks) == 1
        assert blocks[0].content == "> Line 1\n> Line 2\n>\n> Line 3"

    def test_blockquote_multiline_real_world(self):
        """Test real-world multi-line blockquote example."""
        content = """> This is a blockquote that contains important information.
> It can span multiple lines and should be preserved as a single block.

> Another blockquote here with a different point.
"""
        blocks = parse_markdown_to_blocks(content)

        # Should be 2 blocks: first multi-line quote, second single-line quote
        assert len(blocks) == 2
        assert "> This is a blockquote" in blocks[0].content
        assert "> It can span multiple lines" in blocks[0].content
        assert blocks[1].content == "> Another blockquote here with a different point."

    def test_horizontal_rule(self):
        """Test horizontal rule."""
        content = """Some text

---

More text
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 3
        assert blocks[0].content == "Some text"
        assert blocks[1].content == "---"
        assert blocks[2].content == "More text"

    def test_paragraph_joining(self):
        """Test that consecutive lines form a single paragraph."""
        content = """This is a paragraph
that continues on the next line
and finishes here.

This is a new paragraph.
"""
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert "This is a paragraph that continues" in blocks[0].content
        assert "This is a new paragraph" in blocks[1].content

    def test_inline_formatting_preserved(self):
        """Test that inline markdown is preserved."""
        content = "**bold** and *italic* and `code` and [link](url)"
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert "**bold**" in blocks[0].content
        assert "*italic*" in blocks[0].content
        assert "`code`" in blocks[0].content
        assert "[link](url)" in blocks[0].content


class TestParseMarkdownEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self):
        """Test empty content."""
        blocks = parse_markdown_to_blocks("")
        assert blocks == []

    def test_whitespace_only(self):
        """Test whitespace-only content."""
        blocks = parse_markdown_to_blocks("   \n\n   \n")
        assert blocks == []

    def test_complex_document(self):
        """Test a complex real-world document."""
        # Use explicit string concatenation to avoid indentation issues
        content = (
            "# Project Overview\n"
            "\n"
            "This is the introduction.\n"
            "\n"
            "## Goals\n"
            "\n"
            "- Goal 1\n"
            "  - Sub-goal A\n"
            "  - Sub-goal B\n"
            "- Goal 2\n"
            "\n"
            "## Code Sample\n"
            "\n"
            "```python\n"
            "def main():\n"
            '    print("Hello")\n'
            "```\n"
            "\n"
            "## Notes\n"
            "\n"
            "> Important note here\n"
            "\n"
            "---\n"
            "\n"
            "End of document.\n"
        )
        blocks = parse_markdown_to_blocks(content)

        # Should have one root H1
        assert len(blocks) == 1
        assert blocks[0].content == "# Project Overview"

        # H1 should have children including intro paragraph and H2 sections
        children = blocks[0].children
        assert len(children) >= 2  # At least intro and first H2


class TestBlocksToBatchFormat:
    """Tests for converting blocks to Logseq format."""

    def test_simple_blocks(self):
        """Test simple blocks conversion."""
        blocks = [
            BlockNode(content="Block 1"),
            BlockNode(content="Block 2"),
        ]

        result = blocks_to_batch_format(blocks)

        assert len(result) == 2
        assert result[0] == {"content": "Block 1"}
        assert result[1] == {"content": "Block 2"}

    def test_nested_blocks(self):
        """Test nested blocks conversion."""
        blocks = [
            BlockNode(
                content="Parent",
                children=[
                    BlockNode(content="Child 1"),
                    BlockNode(content="Child 2"),
                ],
            )
        ]

        result = blocks_to_batch_format(blocks)

        assert len(result) == 1
        assert result[0]["content"] == "Parent"
        assert "children" in result[0]
        assert len(result[0]["children"]) == 2
        assert result[0]["children"][0]["content"] == "Child 1"

    def test_blocks_with_properties(self):
        """Test blocks with properties."""
        blocks = [
            BlockNode(
                content="Block with props",
                properties={"priority": "high", "tags": ["test"]},
            )
        ]

        result = blocks_to_batch_format(blocks)

        assert result[0]["content"] == "Block with props"
        assert result[0]["properties"] == {"priority": "high", "tags": ["test"]}


class TestParseContent:
    """Tests for the main parse_content entry point."""

    def test_full_document_parsing(self):
        """Test parsing a full document with frontmatter."""
        content = """---
tags: [project]
status: active
---

# My Project

Introduction here.

## Tasks

- Task 1
- Task 2
"""
        result = parse_content(content)

        assert isinstance(result, ParsedContent)
        assert result.properties == {"tags": ["project"], "status": "active"}
        assert len(result.blocks) == 1
        assert result.blocks[0].content == "# My Project"

    def test_no_content(self):
        """Test empty content."""
        result = parse_content("")

        assert result.properties == {}
        assert result.blocks == []

    def test_frontmatter_only(self):
        """Test document with only frontmatter."""
        content = """---
key: value
---
"""
        result = parse_content(content)

        assert result.properties == {"key": "value"}
        assert result.blocks == []

    def test_to_batch_format(self):
        """Test converting ParsedContent to batch format."""
        content = """# Title

- Item 1
- Item 2
"""
        result = parse_content(content)
        batch = result.to_batch_format()

        assert isinstance(batch, list)
        assert len(batch) == 1
        assert batch[0]["content"] == "# Title"


class TestCapitalizedMarkers:
    """Tests for capitalized marker patterns (TODO, DONE, DOING, etc.)."""

    def test_simple_done_marker(self):
        """Test simple DONE marker without children."""
        content = "DONE Complete the task"
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "DONE Complete the task"

    def test_done_marker_with_children(self):
        """Test DONE marker with nested children."""
        content = """DONE Contributed to mcp-logseq
  - Fixed issue #7
  - Added 91 tests"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "DONE Contributed to mcp-logseq"
        assert len(blocks[0].children) == 2
        assert blocks[0].children[0].content == "Fixed issue #7"
        assert blocks[0].children[1].content == "Added 91 tests"

    def test_todo_marker(self):
        """Test TODO marker."""
        content = "TODO Review the PR"
        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "TODO Review the PR"

    def test_custom_markers(self):
        """Test custom capitalized markers (DOING, WAITING, etc.)."""
        content = """DOING Work in progress
  - Step 1 complete

WAITING For review

LATER Maybe someday

NOW Urgent task"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 4
        assert blocks[0].content == "DOING Work in progress"
        assert len(blocks[0].children) == 1
        assert blocks[1].content == "WAITING For review"
        assert blocks[2].content == "LATER Maybe someday"
        assert blocks[3].content == "NOW Urgent task"

    def test_marker_with_deep_nesting(self):
        """Test marker with multiple levels of nesting."""
        content = """DONE Main task
  - Subtask 1
    - Detail A
    - Detail B
  - Subtask 2"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "DONE Main task"
        assert len(blocks[0].children) == 2
        assert len(blocks[0].children[0].children) == 2

    def test_short_codes_not_markers(self):
        """Test that 2-char codes (like state codes) are not treated as markers."""
        content = """CA California location
  - Should not be nested
NY New York office
  - Should not be nested"""

        blocks = parse_markdown_to_blocks(content)

        # Should be 4 blocks (2 paragraphs + 2 lists), not 2 nested structures
        assert len(blocks) == 4

    def test_three_char_minimum(self):
        """Test that 3-char markers work (like NOW)."""
        content = """NOW Do this immediately
  - Urgent detail"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].content == "NOW Do this immediately"
        assert len(blocks[0].children) == 1

    def test_lowercase_not_treated_as_marker(self):
        """Test that lowercase words are not treated as markers."""
        content = """done This should be a paragraph
  - This should be a separate list"""

        blocks = parse_markdown_to_blocks(content)

        # Should be 2 blocks (paragraph + list), not nested
        assert len(blocks) == 2

    def test_marker_mixed_with_checkboxes(self):
        """Test that markers work alongside checkbox items."""
        content = """DONE Custom marker task
  - Detail 1
- [x] Checkbox task
  - Detail 2"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].content == "DONE Custom marker task"
        assert blocks[1].content == "DONE Checkbox task"  # Converted from [x]
        assert len(blocks[0].children) == 1
        assert len(blocks[1].children) == 1

    def test_marker_with_hyphens_and_underscores(self):
        """Test markers with hyphens and underscores."""
        content = """IN-PROGRESS Current work
  - Detail

PRIORITY_HIGH Important task
  - Detail"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].content == "IN-PROGRESS Current work"
        assert blocks[1].content == "PRIORITY_HIGH Important task"

    def test_marker_with_numbers(self):
        """Test markers with numbers."""
        content = """STEP1 First step
  - Detail

PRIORITY2 Second priority
  - Detail"""

        blocks = parse_markdown_to_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].content == "STEP1 First step"
        assert blocks[1].content == "PRIORITY2 Second priority"

    def test_empty_line_breaks_nesting(self):
        """Test that empty lines break nesting context."""
        content = """DONE Task

- Unrelated list"""

        blocks = parse_markdown_to_blocks(content)

        # Should be 2 blocks (marker + separate list), not nested
        assert len(blocks) == 2
        assert blocks[0].content == "DONE Task"
        assert len(blocks[0].children) == 0
        assert blocks[1].content == "Unrelated list"
