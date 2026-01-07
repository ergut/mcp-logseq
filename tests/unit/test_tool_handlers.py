import pytest
from unittest.mock import patch, Mock
from mcp.types import TextContent
from mcp_logseq.tools import (
    CreatePageToolHandler,
    ListPagesToolHandler,
    GetPageContentToolHandler,
    DeletePageToolHandler,
    UpdatePageToolHandler,
    SearchToolHandler,
)


class TestCreatePageToolHandler:
    """Test cases for the new CreatePageToolHandler with block parsing."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = CreatePageToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "create_page"
        assert tool.description is not None
        assert "Create a new page in Logseq" in tool.description
        # New handler only requires title
        assert tool.inputSchema["required"] == ["title"]
        # Should have content, properties as optional
        assert "content" in tool.inputSchema["properties"]
        assert "properties" in tool.inputSchema["properties"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success_with_markdown(self, mock_logseq_class):
        """Test successful page creation with markdown content."""
        # Setup mock
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api

        handler = CreatePageToolHandler()
        args = {"title": "Test Page", "content": "# Heading\n\n- Item 1\n- Item 2"}

        result = handler.run_tool(args)

        # Verify API was called correctly (new method)
        mock_api.create_page_with_blocks.assert_called_once()
        call_args = mock_api.create_page_with_blocks.call_args
        assert call_args[0][0] == "Test Page"  # title
        assert isinstance(call_args[0][1], list)  # blocks

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Successfully created page 'Test Page'" in result[0].text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_frontmatter(self, mock_logseq_class):
        """Test page creation with YAML frontmatter."""
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api

        handler = CreatePageToolHandler()
        args = {"title": "Test Page", "content": "---\ntags: [test]\n---\n\n# Content"}

        result = handler.run_tool(args)

        # Verify properties were extracted and passed
        call_args = mock_api.create_page_with_blocks.call_args
        properties = call_args[0][2]  # third argument is properties
        assert properties.get("tags") == ["test"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_explicit_properties(self, mock_logseq_class):
        """Test page creation with explicit properties argument."""
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api

        handler = CreatePageToolHandler()
        args = {
            "title": "Test Page",
            "content": "Content here",
            "properties": {"priority": "high"},
        }

        result = handler.run_tool(args)

        # Verify properties were passed
        call_args = mock_api.create_page_with_blocks.call_args
        properties = call_args[0][2]
        assert properties.get("priority") == "high"

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_empty_page(self, mock_logseq_class):
        """Test creating empty page (title only)."""
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api

        handler = CreatePageToolHandler()
        args = {"title": "Empty Page"}

        result = handler.run_tool(args)

        # Should create page with empty blocks
        call_args = mock_api.create_page_with_blocks.call_args
        assert call_args[0][0] == "Empty Page"
        assert call_args[0][1] == []  # empty blocks

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    def test_run_tool_missing_title(self):
        """Test tool with missing title."""
        handler = CreatePageToolHandler()

        with pytest.raises(RuntimeError, match="title argument required"):
            handler.run_tool({"content": "Test"})

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_api_error(self, mock_logseq_class):
        """Test tool with API error."""
        mock_api = Mock()
        mock_api.create_page_with_blocks.side_effect = Exception("API Error")
        mock_logseq_class.return_value = mock_api

        handler = CreatePageToolHandler()
        args = {"title": "Test Page", "content": "Test content"}

        with pytest.raises(Exception, match="API Error"):
            handler.run_tool(args)


class TestListPagesToolHandler:
    """Test cases for ListPagesToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = ListPagesToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "list_pages"
        assert tool.description is not None
        assert "Lists all pages in a LogSeq graph" in tool.description
        assert tool.inputSchema["required"] == []

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success_exclude_journals(self, mock_logseq_class):
        """Test successful page listing excluding journals."""
        # Setup mock
        mock_api = Mock()
        mock_api.list_pages.return_value = [
            {"originalName": "Regular Page", "journal?": False},
            {"originalName": "Journal Page", "journal?": True},
            {"name": "Another Page", "journal?": False},
        ]
        mock_logseq_class.return_value = mock_api

        handler = ListPagesToolHandler()
        result = handler.run_tool({"include_journals": False})

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        text = result[0].text

        assert "Regular Page" in text
        assert "Another Page" in text
        assert "Journal Page" not in text
        assert "Total pages: 2" in text
        assert "(excluding journal pages)" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success_include_journals(self, mock_logseq_class):
        """Test successful page listing including journals."""
        # Setup mock
        mock_api = Mock()
        mock_api.list_pages.return_value = [
            {"originalName": "Regular Page", "journal?": False},
            {"originalName": "Journal Page", "journal?": True},
        ]
        mock_logseq_class.return_value = mock_api

        handler = ListPagesToolHandler()
        result = handler.run_tool({"include_journals": True})

        # Verify result
        text = result[0].text
        assert "Regular Page" in text
        assert "Journal Page" in text
        assert "Total pages: 2" in text
        assert "(including journal pages)" in text


class TestGetPageContentToolHandler:
    """Test cases for GetPageContentToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = GetPageContentToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "get_page_content"
        assert tool.description is not None
        assert "Get the content of a specific page" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success_text_format(self, mock_logseq_class):
        """Test successful page content retrieval in text format."""
        # Setup mock - properties are in the first block's content (as Logseq returns them)
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {
                "originalName": "Test Page",
                "properties": {"tags": ["test"], "priority": "high"},
            },
            "blocks": [
                {"content": "Block 1 content\ntags:: [[test]]\npriority:: high"},
                {"content": "Block 2 content"},
            ],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        # Verify result
        assert len(result) == 1
        text = result[0].text

        # Properties shown in content (no YAML frontmatter duplication)
        assert "Block 1 content" in text
        assert "tags:: [[test]]" in text  # Properties in content
        assert "priority:: high" in text  # Properties in content
        assert "Block 2 content" in text
        # No YAML frontmatter
        assert not text.startswith("---")

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success_json_format(self, mock_logseq_class):
        """Test successful page content retrieval in JSON format."""
        # Setup mock
        mock_data = {"page": {"name": "Test"}, "blocks": []}
        mock_api = Mock()
        mock_api.get_page_content.return_value = mock_data
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "json"})

        # Verify result
        assert str(mock_data) in result[0].text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_page_not_found(self, mock_logseq_class):
        """Test page content retrieval for non-existent page."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_page_content.return_value = None
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Non-existent"})

        # Verify result
        assert "Page 'Non-existent' not found" in result[0].text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_nested_blocks_text_format(
        self, mock_logseq_class, mock_logseq_responses
    ):
        """Test page content retrieval with nested blocks (2 levels)."""
        # Setup mock with nested blocks
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {}},
            "blocks": mock_logseq_responses["get_page_blocks_nested"],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        # Verify result
        text = result[0].text
        assert "- DONE Parent task" in text
        assert "  - Child task 1" in text  # Indented with 2 spaces
        assert "  - TODO Child task 2" in text  # Indented with 2 spaces
        assert "    - Grandchild detail" in text  # Indented with 4 spaces

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_deep_nesting_text_format(
        self, mock_logseq_class, mock_logseq_responses
    ):
        """Test page content with deep nesting (3+ levels)."""
        # Setup mock - use the nested data which has 3 levels
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {}},
            "blocks": mock_logseq_responses["get_page_blocks_nested"],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        # Verify all 3 levels appear
        text = result[0].text
        lines = text.split("\n")

        # Find the lines with our content
        parent_line = [l for l in lines if "DONE Parent task" in l][0]
        child_line = [l for l in lines if "TODO Child task 2" in l][0]
        grandchild_line = [l for l in lines if "Grandchild detail" in l][0]

        # Verify indentation levels (count leading spaces before '-')
        assert parent_line.startswith("- DONE Parent task")  # 0 spaces
        assert child_line.startswith("  - TODO Child task 2")  # 2 spaces
        assert grandchild_line.startswith("    - Grandchild detail")  # 4 spaces

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_max_depth_limit(
        self, mock_logseq_class, mock_logseq_responses
    ):
        """Test max_depth parameter limits nesting display."""
        # Setup mock with 3-level nesting
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {}},
            "blocks": mock_logseq_responses["get_page_blocks_nested"],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        # Set max_depth to 1 (show parent + immediate children only)
        result = handler.run_tool(
            {"page_name": "Test Page", "format": "text", "max_depth": 1}
        )

        text = result[0].text

        # Verify parent and children appear
        assert "- DONE Parent task" in text
        assert "  - Child task 1" in text
        assert "  - TODO Child task 2" in text

        # Verify grandchild does NOT appear
        assert "Grandchild detail" not in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_markers_and_properties(
        self, mock_logseq_class, mock_logseq_responses
    ):
        """Test that markers and properties are preserved in content as returned by Logseq."""
        # Setup mock - properties are already in content (as Logseq returns them)
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {}},
            "blocks": [
                {
                    "id": "block-1",
                    "content": "DONE Parent task\npriority:: high",  # Properties in content
                    "marker": "DONE",
                    "properties": {"priority": "high"},
                    "children": [
                        {
                            "id": "block-1-1",
                            "content": "Child task 1",
                            "properties": {},
                            "children": [],
                        },
                        {
                            "id": "block-1-2",
                            "content": "TODO Child task 2\ntags:: [[urgent]]",  # Tags in content
                            "marker": "TODO",
                            "properties": {"tags": ["urgent"]},
                            "children": [
                                {
                                    "id": "block-1-2-1",
                                    "content": "Grandchild detail",
                                    "properties": {},
                                    "children": [],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        text = result[0].text

        # Verify markers are preserved in content
        assert "DONE Parent task" in text
        assert "TODO Child task 2" in text

        # Verify properties are shown as they appear in content (no extra formatting)
        assert "priority:: high" in text  # As Logseq stores it in content
        assert "tags:: [[urgent]]" in text  # As Logseq stores tags in content

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_multiple_children_same_level(
        self, mock_logseq_class, mock_logseq_responses
    ):
        """Test that multiple sibling blocks at the same level are formatted correctly."""
        # Setup mock with multiple siblings
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {}},
            "blocks": mock_logseq_responses["get_page_blocks_multiple_siblings"],
        }
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        text = result[0].text
        lines = text.split("\n")

        # Find all child lines
        child_lines = [
            l for l in lines if l.strip().startswith("- ") and "child" in l.lower()
        ]

        # Should have parent + 3 children = 4 lines with "child" in them
        assert len(child_lines) >= 4

        # Verify all children have same indentation (2 spaces)
        first_child = [l for l in lines if "First child" in l][0]
        second_child = [l for l in lines if "Second child" in l][0]
        third_child = [l for l in lines if "Third child" in l][0]

        assert first_child.startswith("  - First child")
        assert second_child.startswith("  - Second child")
        assert third_child.startswith("  - Third child")


class TestDeletePageToolHandler:
    """Test cases for DeletePageToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = DeletePageToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "delete_page"
        assert tool.description is not None
        assert "Delete a page from LogSeq" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful page deletion."""
        # Setup mock
        mock_api = Mock()
        mock_api.delete_page.return_value = {"success": True}
        mock_logseq_class.return_value = mock_api

        handler = DeletePageToolHandler()
        result = handler.run_tool({"page_name": "Test Page"})

        # Verify API was called
        mock_api.delete_page.assert_called_once_with("Test Page")

        # Verify result
        text = result[0].text
        assert "✅ Successfully deleted page 'Test Page'" in text
        assert "🗑️  Page 'Test Page' has been permanently removed" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_page_not_found(self, mock_logseq_class):
        """Test deletion of non-existent page."""
        # Setup mock to raise ValueError
        mock_api = Mock()
        mock_api.delete_page.side_effect = ValueError("Page 'Test' does not exist")
        mock_logseq_class.return_value = mock_api

        handler = DeletePageToolHandler()
        result = handler.run_tool({"page_name": "Test"})

        # Verify error handling
        text = result[0].text
        assert "❌ Error: Page 'Test' does not exist" in text


class TestUpdatePageToolHandler:
    """Test cases for the new UpdatePageToolHandler with block parsing."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = UpdatePageToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "update_page"
        assert tool.description is not None
        assert "Update a page in Logseq" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]
        # Should have mode parameter
        assert "mode" in tool.inputSchema["properties"]
        assert tool.inputSchema["properties"]["mode"]["enum"] == ["append", "replace"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_append_mode(self, mock_logseq_class):
        """Test page update in append mode (default)."""
        mock_api = Mock()
        mock_api.update_page_with_blocks.return_value = {
            "updates": [("blocks_appended", 2)],
            "page": "Test Page",
        }
        mock_logseq_class.return_value = mock_api

        handler = UpdatePageToolHandler()
        result = handler.run_tool(
            {"page_name": "Test Page", "content": "# New Content\n\n- Item 1"}
        )

        # Verify API was called with append mode
        call_args = mock_api.update_page_with_blocks.call_args
        assert call_args[1]["mode"] == "append"

        # Verify result
        text = result[0].text
        assert "Successfully updated page 'Test Page'" in text
        assert "Mode: append" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_replace_mode(self, mock_logseq_class):
        """Test page update in replace mode."""
        mock_api = Mock()
        mock_api.update_page_with_blocks.return_value = {
            "updates": [("cleared", True), ("blocks_replaced", 3)],
            "page": "Test Page",
        }
        mock_logseq_class.return_value = mock_api

        handler = UpdatePageToolHandler()
        result = handler.run_tool(
            {
                "page_name": "Test Page",
                "content": "# Replaced Content",
                "mode": "replace",
            }
        )

        # Verify API was called with replace mode
        call_args = mock_api.update_page_with_blocks.call_args
        assert call_args[1]["mode"] == "replace"

        # Verify result mentions clearing
        text = result[0].text
        assert "Mode: replace" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_properties(self, mock_logseq_class):
        """Test page update with properties."""
        mock_api = Mock()
        mock_api.update_page_with_blocks.return_value = {
            "updates": [("properties", {"priority": "high"})],
            "page": "Test Page",
        }
        mock_logseq_class.return_value = mock_api

        handler = UpdatePageToolHandler()
        result = handler.run_tool(
            {"page_name": "Test Page", "properties": {"priority": "high"}}
        )

        # Verify properties were passed
        call_args = mock_api.update_page_with_blocks.call_args
        assert call_args[0][2] == {"priority": "high"}

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    def test_run_tool_no_updates(self):
        """Test update with no content or properties."""
        handler = UpdatePageToolHandler()
        result = handler.run_tool({"page_name": "Test Page"})

        # Verify error handling
        text = result[0].text
        assert "Error: Either 'content' or 'properties' must be provided" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_page_not_found(self, mock_logseq_class):
        """Test update on non-existent page."""
        mock_api = Mock()
        mock_api.update_page_with_blocks.side_effect = ValueError(
            "Page 'Test' does not exist"
        )
        mock_logseq_class.return_value = mock_api

        handler = UpdatePageToolHandler()
        result = handler.run_tool({"page_name": "Test", "content": "New content"})

        text = result[0].text
        assert "Error: Page 'Test' does not exist" in text


class TestSearchToolHandler:
    """Test cases for SearchToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = SearchToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "search"
        assert tool.description is not None
        assert "Search for content across LogSeq pages" in tool.description
        assert tool.inputSchema["required"] == ["query"]

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful search."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = {
            "blocks": [{"block/content": "Found content"}],
            "pages": ["Matching Page"],
            "pages-content": [{"block/snippet": "Snippet content"}],
            "files": [],
            "has-more?": False,
        }
        mock_logseq_class.return_value = mock_api

        handler = SearchToolHandler()
        result = handler.run_tool({"query": "test"})

        # Verify API was called
        mock_api.search_content.assert_called_once_with("test", {"limit": 20})

        # Verify result
        text = result[0].text
        assert "# Search Results for 'test'" in text
        assert "📄 Content Blocks (1 found)" in text
        assert "Found content" in text
        assert "📑 Matching Pages (1 found)" in text
        assert "Matching Page" in text
        assert "Total results found: 2" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_no_results(self, mock_logseq_class):
        """Test search with no results."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = None
        mock_logseq_class.return_value = mock_api

        handler = SearchToolHandler()
        result = handler.run_tool({"query": "nothing"})

        # Verify result
        text = result[0].text
        assert "No search results found for 'nothing'" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_run_tool_with_options(self, mock_logseq_class):
        """Test search with custom options."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = {"blocks": [], "pages": [], "files": []}
        mock_logseq_class.return_value = mock_api

        handler = SearchToolHandler()
        result = handler.run_tool(
            {
                "query": "test",
                "limit": 5,
                "include_blocks": False,
                "include_files": True,
            }
        )

        # Verify API was called with correct options
        mock_api.search_content.assert_called_once_with("test", {"limit": 5})
