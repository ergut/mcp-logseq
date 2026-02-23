import pytest
import asyncio
from unittest.mock import patch, Mock, AsyncMock
from mcp.types import Tool, TextContent
from mcp_logseq.server import app, tool_handlers, add_tool_handler, get_tool_handler


class TestMCPServerIntegration:
    """Integration tests for the MCP server."""

    def test_tool_handlers_registration(self):
        """Test that all tool handlers are properly registered."""
        expected_tools = [
            "create_page",
            "list_pages",
            "get_page_content",
            "delete_page",
            "update_page",
            "search",
        ]

        # Verify all expected tools are registered
        for tool_name in expected_tools:
            assert tool_name in tool_handlers
            handler = get_tool_handler(tool_name)
            assert handler is not None
            assert hasattr(handler, "run_tool")
            assert hasattr(handler, "get_tool_description")

    def test_get_tool_handler_existing(self):
        """Test retrieving an existing tool handler."""
        handler = get_tool_handler("create_page")
        assert handler is not None
        assert handler.name == "create_page"

    def test_get_tool_handler_non_existing(self):
        """Test retrieving a non-existing tool handler."""
        handler = get_tool_handler("non_existing_tool")
        assert handler is None

    def test_list_tools_handler_count(self):
        """Test that we have the expected number of tool handlers."""
        # We should have 6 registered tool handlers
        assert len(tool_handlers) == 6

        # Verify core tool names are present
        core_tools = [
            "create_page",
            "list_pages",
            "get_page_content",
            "delete_page",
            "update_page",
            "search",
        ]
        for name in core_tools:
            assert name in tool_handlers

        # Verify each handler can generate a tool description
        for handler in tool_handlers.values():
            tool_desc = handler.get_tool_description()
            assert isinstance(tool_desc, Tool)
            assert hasattr(tool_desc, "name")
            assert hasattr(tool_desc, "description")
            assert hasattr(tool_desc, "inputSchema")

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_call_tool_success_integration(self, mock_logseq_class):
        """Test successful tool call execution through handler."""
        # Setup mock
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api

        # Test create_page tool directly through handler (new version)
        handler = get_tool_handler("create_page")
        assert handler is not None
        result = handler.run_tool({"title": "Test Page", "content": "Test content"})

        # Verify result
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Successfully created page 'Test Page'" in result[0].text

        # Verify API was called (new handler uses create_page_with_blocks)
        mock_api.create_page_with_blocks.assert_called_once()

    def test_call_tool_unknown_tool_integration(self):
        """Test calling an unknown tool through handler system."""
        handler = get_tool_handler("unknown_tool")
        assert handler is None

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_call_tool_handler_error_integration(self, mock_logseq_class):
        """Test tool call when handler raises an exception."""
        # Setup mock to raise exception (new handler uses create_page_with_blocks)
        mock_api = Mock()
        mock_api.create_page_with_blocks.side_effect = Exception("API Error")
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("create_page")
        assert handler is not None
        with pytest.raises(Exception, match="API Error"):
            handler.run_tool({"title": "Test Page", "content": "Test content"})

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_list_pages_tool_integration(self, mock_logseq_class):
        """Test list_pages tool end-to-end."""
        # Setup mock
        mock_api = Mock()
        mock_api.list_pages.return_value = [
            {"originalName": "Page 1", "journal?": False},
            {"originalName": "Page 2", "journal?": False},
        ]
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("list_pages")
        assert handler is not None
        result = handler.run_tool({"include_journals": False})

        # Verify result structure
        assert len(result) == 1
        text = result[0].text
        assert "Page 1" in text
        assert "Page 2" in text
        assert "Total pages: 2" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_get_page_content_tool_integration(self, mock_logseq_class):
        """Test get_page_content tool end-to-end."""
        # Setup mock - properties in content (as Logseq returns them)
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"originalName": "Test Page", "properties": {"priority": "high"}},
            "blocks": [{"content": "Test content\npriority:: high"}],
        }
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("get_page_content")
        assert handler is not None
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})

        # Verify result structure
        assert len(result) == 1
        text = result[0].text
        # Properties shown in content (no YAML frontmatter)
        assert "Test content" in text
        assert "priority:: high" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_search_tool_integration(self, mock_logseq_class):
        """Test search tool end-to-end."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = {
            "blocks": [{"block/content": "Found content"}],
            "pages": ["Matching Page"],
            "pages-content": [],
            "files": [],
            "has-more?": False,
        }
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("search")
        assert handler is not None
        result = handler.run_tool({"query": "test search"})

        # Verify result structure
        assert len(result) == 1
        text = result[0].text
        assert "Search Results for 'test search'" in text
        assert "Found content" in text
        assert "Matching Page" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_delete_page_tool_integration(self, mock_logseq_class):
        """Test delete_page tool end-to-end."""
        # Setup mock
        mock_api = Mock()
        mock_api.delete_page.return_value = {"success": True}
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("delete_page")
        assert handler is not None
        result = handler.run_tool({"page_name": "Test Page"})

        # Verify result structure
        assert len(result) == 1
        text = result[0].text
        assert "✅ Successfully deleted page 'Test Page'" in text
        assert "🗑️  Page 'Test Page' has been permanently removed" in text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_update_page_tool_integration(self, mock_logseq_class):
        """Test update_page tool end-to-end."""
        # Setup mock (new handler uses update_page_with_blocks)
        mock_api = Mock()
        mock_api.update_page_with_blocks.return_value = {
            "updates": [("blocks_appended", 1)],
            "page": "Test Page",
        }
        mock_logseq_class.return_value = mock_api

        handler = get_tool_handler("update_page")
        assert handler is not None
        result = handler.run_tool({"page_name": "Test Page", "content": "New content"})

        # Verify result structure
        assert len(result) == 1
        text = result[0].text
        assert "Successfully updated page 'Test Page'" in text
        assert "Mode: append" in text

    def test_add_tool_handler_custom(self):
        """Test adding a custom tool handler."""
        from mcp_logseq.tools import ToolHandler
        from mcp.types import Tool, TextContent

        class CustomToolHandler(ToolHandler):
            def __init__(self):
                super().__init__("custom_tool")

            def get_tool_description(self):
                return Tool(
                    name=self.name,
                    description="Custom test tool",
                    inputSchema={"type": "object", "properties": {}, "required": []},
                )

            def run_tool(self, args: dict):
                return [TextContent(type="text", text="Custom tool result")]

        # Add custom handler
        custom_handler = CustomToolHandler()
        original_count = len(tool_handlers)
        add_tool_handler(custom_handler)

        # Verify it was added
        assert len(tool_handlers) == original_count + 1
        assert "custom_tool" in tool_handlers
        assert get_tool_handler("custom_tool") == custom_handler

        # Clean up
        del tool_handlers["custom_tool"]

    def test_tool_handler_interface_compliance(self):
        """Test that all registered tool handlers implement the required interface."""
        for name, handler in tool_handlers.items():
            # Check required methods exist
            assert hasattr(handler, "get_tool_description")
            assert hasattr(handler, "run_tool")
            assert hasattr(handler, "name")

            # Check name attribute matches
            assert handler.name == name

            # Check get_tool_description returns a Tool
            tool_desc = handler.get_tool_description()
            assert isinstance(tool_desc, Tool)
            assert tool_desc.name == name
