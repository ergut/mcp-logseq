"""
Markdown to Logseq Block Parser

This module converts markdown content into Logseq's block tree structure,
supporting headings, lists, code blocks, blockquotes, and YAML frontmatter.
"""

from dataclasses import dataclass, field
from typing import Any
import re
import logging
import datetime

import yaml

logger = logging.getLogger("mcp-logseq")


@dataclass
class BlockNode:
    """Represents a Logseq block with potential children."""

    content: str
    children: list["BlockNode"] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    level: int = 0

    def to_batch_format(self) -> dict[str, Any]:
        """Convert to Logseq IBatchBlock format."""
        result: dict[str, Any] = {"content": self.content}

        if self.children:
            result["children"] = [child.to_batch_format() for child in self.children]

        if self.properties:
            result["properties"] = self.properties

        return result


@dataclass
class ParsedContent:
    """Result of parsing markdown content."""

    properties: dict[str, Any] = field(default_factory=dict)
    blocks: list[BlockNode] = field(default_factory=list)

    def to_batch_format(self) -> list[dict[str, Any]]:
        """Convert all blocks to Logseq IBatchBlock format."""
        return [block.to_batch_format() for block in self.blocks]


# Regex patterns for markdown elements
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
BULLET_PATTERN = re.compile(r"^(\s*)([-*+])\s+(.*)$")
NUMBERED_PATTERN = re.compile(r"^(\s*)(\d+\.)\s+(.*)$")
CHECKBOX_PATTERN = re.compile(r"^(\s*)([-*+])\s+\[([ xX])\]\s+(.*)$")
CAPITALIZED_MARKER_PATTERN = re.compile(r"^(\s*)([A-Z][A-Z0-9_-]{2,})\s+(.+)$")
BLOCKQUOTE_PATTERN = re.compile(r"^(\s*)(>+)\s*(.*)$")
HORIZONTAL_RULE_PATTERN = re.compile(r"^(\s*)[-*_]{3,}\s*$")
FENCED_CODE_START = re.compile(r"^(\s*)```(\w*)(.*)$")
FENCED_CODE_END = re.compile(r"^(\s*)```\s*$")


def _serialize_frontmatter_value(obj: Any) -> Any:
    """
    Convert non-JSON-serializable types to strings.

    PyYAML's safe_load() automatically converts date-like strings to
    datetime.date objects, which aren't JSON serializable. This function
    converts them to ISO format strings.
    """
    if isinstance(obj, dict):
        return {k: _serialize_frontmatter_value(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_frontmatter_value(item) for item in obj]
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Extract YAML frontmatter from content.

    Args:
        content: Raw markdown content

    Returns:
        Tuple of (properties dict, remaining content without frontmatter)
    """
    if not content.startswith("---"):
        return {}, content

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content

    yaml_content = match.group(1)
    remaining_content = content[match.end() :]

    try:
        properties = yaml.safe_load(yaml_content)
        if properties is None:
            properties = {}
        elif not isinstance(properties, dict):
            logger.warning(f"Frontmatter is not a dict, ignoring: {type(properties)}")
            properties = {}
        else:
            # Convert any date/datetime objects to ISO strings for JSON serialization
            properties = _serialize_frontmatter_value(properties)
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        properties = {}

    return properties, remaining_content


def _get_indent_level(line: str) -> int:
    """
    Calculate the indentation level of a line.

    2 spaces = 1 level, 4 spaces = 2 levels, etc.
    Tabs are treated as 2 spaces.
    """
    spaces = 0
    for char in line:
        if char == " ":
            spaces += 1
        elif char == "\t":
            spaces += 2
        else:
            break
    return spaces // 2


def _get_heading_level(line: str) -> int:
    """Get the heading level (1-6) or 0 if not a heading."""
    match = HEADING_PATTERN.match(line)
    if match:
        return len(match.group(1))
    return 0


def _parse_list_item_content(line: str) -> tuple[str, int]:
    """
    Extract content from a list item line.

    List markers (-, *, +, 1., etc.) are stripped because Logseq blocks
    are already rendered as bullets. Including the marker would create
    redundant bullet points.

    Checkboxes are converted to Logseq's TODO/DONE syntax.

    Returns tuple of (formatted_content, indent_level).
    """
    indent_level = _get_indent_level(line)

    # Check for checkbox - convert to Logseq TODO/DONE format
    checkbox_match = CHECKBOX_PATTERN.match(line)
    if checkbox_match:
        _, marker, check, text = checkbox_match.groups()
        # Logseq uses TODO and DONE keywords
        status = "DONE" if check.lower() == "x" else "TODO"
        # Strip redundant TODO:/DONE: prefix from text if present
        text = text.strip()
        if text.startswith("TODO:") or text.startswith("DONE:"):
            text = text.split(":", 1)[1].strip()
        return f"{status} {text}", indent_level

    # Check for bullet - strip the marker, keep only text
    bullet_match = BULLET_PATTERN.match(line)
    if bullet_match:
        _, marker, text = bullet_match.groups()
        return text, indent_level

    # Check for numbered - strip the number, keep only text
    numbered_match = NUMBERED_PATTERN.match(line)
    if numbered_match:
        _, number, text = numbered_match.groups()
        return text, indent_level

    # Check for capitalized marker (TODO, DONE, DOING, etc.)
    marker_match = CAPITALIZED_MARKER_PATTERN.match(line)
    if marker_match:
        _, marker, text = marker_match.groups()
        return f"{marker} {text}", indent_level

    # Fallback
    return line.strip(), indent_level


class MarkdownParser:
    """
    Stateful parser for converting markdown to block tree.

    Handles:
    - Headings (H1-H6) with hierarchy
    - Bullet lists (-, *, +) with nesting
    - Numbered lists (1., 2., etc.)
    - Checkboxes (- [ ] or - [x])
    - Fenced code blocks (```)
    - Blockquotes (>)
    - Horizontal rules (---, ***, ___)
    - Paragraphs
    """

    def __init__(self):
        self.blocks: list[BlockNode] = []
        self.heading_stack: list[
            BlockNode
        ] = []  # Stack of heading blocks for hierarchy
        self.current_heading_level: int = 0

    def parse(self, content: str) -> list[BlockNode]:
        """
        Parse markdown content into a list of BlockNodes.

        Args:
            content: Markdown content (without frontmatter)

        Returns:
            List of root-level BlockNodes
        """
        if not content or not content.strip():
            return []

        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Check for fenced code block
            code_match = FENCED_CODE_START.match(line)
            if code_match:
                i = self._parse_fenced_code(lines, i)
                continue

            # Check for heading
            heading_level = _get_heading_level(line)
            if heading_level > 0:
                self._parse_heading(line, heading_level)
                i += 1
                continue

            # Check for horizontal rule
            if HORIZONTAL_RULE_PATTERN.match(line):
                self._add_block(BlockNode(content="---", level=0))
                i += 1
                continue

            # Check for blockquote
            quote_match = BLOCKQUOTE_PATTERN.match(line)
            if quote_match:
                i = self._parse_blockquote(lines, i)
                continue

            # Check for list items (checkbox, bullet, numbered, or capitalized marker)
            if (
                CHECKBOX_PATTERN.match(line)
                or BULLET_PATTERN.match(line)
                or NUMBERED_PATTERN.match(line)
                or CAPITALIZED_MARKER_PATTERN.match(line)
            ):
                i = self._parse_list_item(lines, i)
                continue

            # Default: paragraph
            i = self._parse_paragraph(lines, i)

        return self.blocks

    def _parse_heading(self, line: str, level: int) -> None:
        """Parse a heading line and update hierarchy."""
        match = HEADING_PATTERN.match(line)
        if not match:
            return

        # Keep the # prefix as requested
        heading_text = line.strip()
        heading_block = BlockNode(content=heading_text, level=level)

        # Update heading stack for proper hierarchy
        # Pop headings of same or higher level (lower priority)
        while self.heading_stack and self.heading_stack[-1].level >= level:
            self.heading_stack.pop()

        if self.heading_stack:
            # This heading is a child of the previous heading in stack
            parent = self.heading_stack[-1]
            parent.children.append(heading_block)
        else:
            # This is a root-level heading
            self.blocks.append(heading_block)

        # Push this heading onto the stack
        self.heading_stack.append(heading_block)
        self.current_heading_level = level

    def _parse_fenced_code(self, lines: list[str], start: int) -> int:
        """
        Parse a fenced code block.

        Returns the index of the line after the closing fence.
        """
        code_lines = [lines[start]]  # Include opening fence
        i = start + 1

        while i < len(lines):
            code_lines.append(lines[i])
            if FENCED_CODE_END.match(lines[i]):
                break
            i += 1

        # Create single block with entire code content
        code_content = "\n".join(code_lines)
        self._add_block(BlockNode(content=code_content, level=0))

        return i + 1

    def _parse_blockquote(self, lines: list[str], start: int) -> int:
        """
        Parse blockquote lines.

        Contiguous blockquote lines (lines starting with >) are joined into
        a single block. An empty line (not starting with >) ends the blockquote.

        Example:
            > Line 1
            > Line 2
            >
            > Line 3

        Becomes a single block: "> Line 1\\n> Line 2\\n>\\n> Line 3"

        But:
            > Line 1

            > Line 2

        Becomes two separate blocks.
        """
        i = start
        quote_lines = []

        while i < len(lines):
            line = lines[i]
            match = BLOCKQUOTE_PATTERN.match(line)
            if match:
                # Keep the > prefix as part of content
                quote_lines.append(line.rstrip())
                i += 1
            else:
                # Non-blockquote line ends this blockquote
                break

        # Join all contiguous blockquote lines into a single block
        if quote_lines:
            quote_content = "\n".join(quote_lines)
            self._add_block(BlockNode(content=quote_content, level=0))

        return i

    def _parse_list_item(self, lines: list[str], start: int) -> int:
        """
        Parse a list item and its nested children.

        Returns the index of the next line to process.
        """
        line = lines[start]
        item_content, indent_level = _parse_list_item_content(line)

        list_block = BlockNode(content=item_content, level=indent_level)

        i = start + 1

        # Look for nested items (items with greater indentation)
        while i < len(lines):
            next_line = lines[i]

            # Skip empty lines within list
            if not next_line.strip():
                i += 1
                continue

            next_indent = _get_indent_level(next_line)

            # If less or equal indent, this item is done
            if next_indent <= indent_level:
                # Check if it's still a list item at same level
                if next_indent == indent_level:
                    if (
                        BULLET_PATTERN.match(next_line)
                        or NUMBERED_PATTERN.match(next_line)
                        or CHECKBOX_PATTERN.match(next_line)
                        or CAPITALIZED_MARKER_PATTERN.match(next_line)
                    ):
                        break
                else:
                    break

            # Check if it's a special element (heading, code, etc.) - if so, stop list parsing
            if (
                HEADING_PATTERN.match(next_line)
                or FENCED_CODE_START.match(next_line)
                or HORIZONTAL_RULE_PATTERN.match(next_line)
                or BLOCKQUOTE_PATTERN.match(next_line)
            ):
                break

            # Nested content - parse recursively
            if (
                CHECKBOX_PATTERN.match(next_line)
                or BULLET_PATTERN.match(next_line)
                or NUMBERED_PATTERN.match(next_line)
                or CAPITALIZED_MARKER_PATTERN.match(next_line)
            ):
                nested_block, i = self._parse_nested_list_item(lines, i, indent_level)
                list_block.children.append(nested_block)
            else:
                # Continuation text or other content under this list item
                nested_block = BlockNode(content=next_line.strip(), level=next_indent)
                list_block.children.append(nested_block)
                i += 1

        self._add_block(list_block)
        return i

    def _parse_nested_list_item(
        self, lines: list[str], start: int, parent_indent: int
    ) -> tuple[BlockNode, int]:
        """
        Parse a nested list item and return it without adding to root blocks.

        Returns tuple of (BlockNode, next_line_index).
        """
        line = lines[start]
        item_content, indent_level = _parse_list_item_content(line)

        list_block = BlockNode(content=item_content, level=indent_level)

        i = start + 1

        # Look for nested items
        while i < len(lines):
            next_line = lines[i]

            if not next_line.strip():
                i += 1
                continue

            next_indent = _get_indent_level(next_line)

            # If indent is back to our level or less, we're done
            if next_indent <= indent_level:
                break

            # Check if it's a special element - if so, stop list parsing
            if (
                HEADING_PATTERN.match(next_line)
                or FENCED_CODE_START.match(next_line)
                or HORIZONTAL_RULE_PATTERN.match(next_line)
                or BLOCKQUOTE_PATTERN.match(next_line)
            ):
                break

            # Deeper nested content
            if (
                CHECKBOX_PATTERN.match(next_line)
                or BULLET_PATTERN.match(next_line)
                or NUMBERED_PATTERN.match(next_line)
                or CAPITALIZED_MARKER_PATTERN.match(next_line)
            ):
                nested_block, i = self._parse_nested_list_item(lines, i, indent_level)
                list_block.children.append(nested_block)
            else:
                nested_block = BlockNode(content=next_line.strip(), level=next_indent)
                list_block.children.append(nested_block)
                i += 1

        return list_block, i

    def _parse_paragraph(self, lines: list[str], start: int) -> int:
        """
        Parse a paragraph (consecutive non-special lines).

        Returns the index of the next line to process.
        """
        paragraph_lines = []
        i = start

        while i < len(lines):
            line = lines[i]

            # Empty line ends paragraph
            if not line.strip():
                break

            # Check if this line starts a special element
            if (
                HEADING_PATTERN.match(line)
                or BULLET_PATTERN.match(line)
                or NUMBERED_PATTERN.match(line)
                or CHECKBOX_PATTERN.match(line)
                or BLOCKQUOTE_PATTERN.match(line)
                or HORIZONTAL_RULE_PATTERN.match(line)
                or FENCED_CODE_START.match(line)
            ):
                break

            paragraph_lines.append(line.strip())
            i += 1

        if paragraph_lines:
            # Join paragraph lines into single block
            paragraph_content = " ".join(paragraph_lines)
            self._add_block(BlockNode(content=paragraph_content, level=0))

        return i

    def _add_block(self, block: BlockNode) -> None:
        """
        Add a block to the appropriate place in the hierarchy.

        If there's a current heading context, add as child of that heading.
        Otherwise, add as root block.
        """
        if self.heading_stack:
            # Add as child of current heading
            self.heading_stack[-1].children.append(block)
        else:
            # Add as root block
            self.blocks.append(block)


def parse_markdown_to_blocks(content: str) -> list[BlockNode]:
    """
    Parse markdown content into a tree of BlockNodes.

    Args:
        content: Markdown content (without frontmatter)

    Returns:
        List of root-level BlockNodes
    """
    parser = MarkdownParser()
    return parser.parse(content)


def blocks_to_batch_format(blocks: list[BlockNode]) -> list[dict[str, Any]]:
    """
    Convert BlockNode tree to Logseq IBatchBlock format.

    Args:
        blocks: List of BlockNodes

    Returns:
        List of dicts with 'content', 'children', 'properties' keys
    """
    return [block.to_batch_format() for block in blocks]


def parse_content(content: str) -> ParsedContent:
    """
    Main entry point: parse markdown with frontmatter.

    Args:
        content: Full markdown content including optional frontmatter

    Returns:
        ParsedContent with properties (from frontmatter) and block tree
    """
    if not content or not content.strip():
        return ParsedContent()

    # Extract frontmatter
    properties, remaining_content = parse_frontmatter(content)

    # Parse remaining content into blocks
    blocks = parse_markdown_to_blocks(remaining_content)

    return ParsedContent(properties=properties, blocks=blocks)
