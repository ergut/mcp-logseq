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
    GetPagesFromNamespaceToolHandler,
    GetPagesTreeFromNamespaceToolHandler,
    RenamePageToolHandler,
    GetPageBacklinksToolHandler
)

class TestCreatePageToolHandler:
    """Test cases for CreatePageToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = CreatePageToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "create_page"
        assert "Create a new page in LogSeq" in tool.description
        assert tool.inputSchema["required"] == ["title", "content"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful page creation."""
        # Setup mock
        mock_api = Mock()
        mock_logseq_class.return_value = mock_api
        
        handler = CreatePageToolHandler()
        args = {"title": "Test Page", "content": "Test content"}
        
        result = handler.run_tool(args)
        
        # Verify API was called correctly
        mock_api.create_page.assert_called_once_with("Test Page", "Test content")
        
        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Successfully created page 'Test Page'" in result[0].text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_missing_args(self):
        """Test tool with missing required arguments."""
        handler = CreatePageToolHandler()
        
        with pytest.raises(RuntimeError, match="title and content arguments required"):
            handler.run_tool({"title": "Test"})  # Missing content
        
        with pytest.raises(RuntimeError, match="title and content arguments required"):
            handler.run_tool({"content": "Test"})  # Missing title

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_api_error(self, mock_logseq_class):
        """Test tool with API error."""
        # Setup mock to raise exception
        mock_api = Mock()
        mock_api.create_page.side_effect = Exception("API Error")
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
        assert "Lists all pages in a LogSeq graph" in tool.description
        assert tool.inputSchema["required"] == []

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success_exclude_journals(self, mock_logseq_class):
        """Test successful page listing excluding journals."""
        # Setup mock
        mock_api = Mock()
        mock_api.list_pages.return_value = [
            {"originalName": "Regular Page", "journal?": False},
            {"originalName": "Journal Page", "journal?": True},
            {"name": "Another Page", "journal?": False}
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

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success_include_journals(self, mock_logseq_class):
        """Test successful page listing including journals."""
        # Setup mock
        mock_api = Mock()
        mock_api.list_pages.return_value = [
            {"originalName": "Regular Page", "journal?": False},
            {"originalName": "Journal Page", "journal?": True}
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
        assert "Get the content of a specific page" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success_text_format(self, mock_logseq_class):
        """Test successful page content retrieval in text format."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {
                "originalName": "Test Page",
                "properties": {"tags": ["test"], "priority": "high"}
            },
            "blocks": [
                {"content": "Block 1 content"},
                {"content": "Block 2 content"}
            ]
        }
        mock_logseq_class.return_value = mock_api
        
        handler = GetPageContentToolHandler()
        result = handler.run_tool({"page_name": "Test Page", "format": "text"})
        
        # Verify result
        assert len(result) == 1
        text = result[0].text
        
        assert "# Test Page" in text
        assert "tags: ['test']" in text
        assert "priority: high" in text
        assert "Block 1 content" in text
        assert "Block 2 content" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
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

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
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


class TestDeletePageToolHandler:
    """Test cases for DeletePageToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = DeletePageToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "delete_page"
        assert "Delete a page from LogSeq" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
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

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
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
    """Test cases for UpdatePageToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = UpdatePageToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "update_page"
        assert "Update a page in LogSeq" in tool.description
        assert tool.inputSchema["required"] == ["page_name"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful page update."""
        # Setup mock
        mock_api = Mock()
        mock_api.update_page.return_value = {
            "updates": [("properties", {"success": True}), ("content", {"success": True})],
            "page": "Test Page"
        }
        mock_logseq_class.return_value = mock_api
        
        handler = UpdatePageToolHandler()
        result = handler.run_tool({
            "page_name": "Test Page",
            "content": "New content",
            "properties": {"priority": "high"}
        })
        
        # Verify API was called
        mock_api.update_page.assert_called_once_with(
            "Test Page", 
            content="New content", 
            properties={"priority": "high"}
        )
        
        # Verify result
        text = result[0].text
        assert "✅ Successfully updated page 'Test Page'" in text
        assert "📝 Properties updated" in text
        assert "📄 Content appended" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_no_updates(self):
        """Test update with no content or properties."""
        handler = UpdatePageToolHandler()
        result = handler.run_tool({"page_name": "Test Page"})
        
        # Verify error handling
        text = result[0].text
        assert "❌ Error: Either 'content' or 'properties' must be provided" in text


class TestSearchToolHandler:
    """Test cases for SearchToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = SearchToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "search"
        assert "Search for content across LogSeq pages" in tool.description
        assert tool.inputSchema["required"] == ["query"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful search."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = {
            "blocks": [{"block/content": "Found content"}],
            "pages": ["Matching Page"],
            "pages-content": [{"block/snippet": "Snippet content"}],
            "files": [],
            "has-more?": False
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

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
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

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_with_options(self, mock_logseq_class):
        """Test search with custom options."""
        # Setup mock
        mock_api = Mock()
        mock_api.search_content.return_value = {"blocks": [], "pages": [], "files": []}
        mock_logseq_class.return_value = mock_api
        
        handler = SearchToolHandler()
        result = handler.run_tool({
            "query": "test",
            "limit": 5,
            "include_blocks": False,
            "include_files": True
        })
        
        # Verify API was called with correct options
        mock_api.search_content.assert_called_once_with("test", {"limit": 5})


class TestGetPagesFromNamespaceToolHandler:
    """Test cases for GetPagesFromNamespaceToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = GetPagesFromNamespaceToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "get_pages_from_namespace"
        assert "namespace" in tool.description.lower()
        assert "namespace" in tool.inputSchema["properties"]
        assert "namespace" in tool.inputSchema["required"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful namespace pages retrieval."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_pages_from_namespace.return_value = [
            {"originalName": "Customer/InsideOut"},
            {"originalName": "Customer/Orienteme"}
        ]
        mock_logseq_class.return_value = mock_api

        handler = GetPagesFromNamespaceToolHandler()
        result = handler.run_tool({"namespace": "Customer"})

        # Verify API was called correctly
        mock_api.get_pages_from_namespace.assert_called_once_with("Customer")

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        text = result[0].text
        assert "Customer/InsideOut" in text
        assert "Customer/Orienteme" in text
        assert "Total: 2 pages" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_empty_namespace(self, mock_logseq_class):
        """Test namespace with no pages."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_pages_from_namespace.return_value = []
        mock_logseq_class.return_value = mock_api

        handler = GetPagesFromNamespaceToolHandler()
        result = handler.run_tool({"namespace": "EmptyNamespace"})

        # Verify result
        text = result[0].text
        assert "No pages found in namespace 'EmptyNamespace'" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_missing_args(self):
        """Test tool with missing namespace argument."""
        handler = GetPagesFromNamespaceToolHandler()

        with pytest.raises(RuntimeError, match="namespace argument required"):
            handler.run_tool({})


class TestGetPagesTreeFromNamespaceToolHandler:
    """Test cases for GetPagesTreeFromNamespaceToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = GetPagesTreeFromNamespaceToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "get_pages_tree_from_namespace"
        assert "tree" in tool.description.lower()
        assert "namespace" in tool.inputSchema["properties"]
        assert "namespace" in tool.inputSchema["required"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful namespace tree retrieval."""
        # Setup mock with hierarchical data
        mock_api = Mock()
        mock_api.get_pages_tree_from_namespace.return_value = [
            {
                "originalName": "Projects/2024",
                "children": [
                    {"originalName": "Projects/2024/ClientA", "children": []},
                    {"originalName": "Projects/2024/ClientB", "children": []}
                ]
            },
            {
                "originalName": "Projects/Archive",
                "children": []
            }
        ]
        mock_logseq_class.return_value = mock_api

        handler = GetPagesTreeFromNamespaceToolHandler()
        result = handler.run_tool({"namespace": "Projects"})

        # Verify API was called correctly
        mock_api.get_pages_tree_from_namespace.assert_called_once_with("Projects")

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        text = result[0].text
        assert "Projects/2024" in text
        assert "Projects/2024/ClientA" in text
        assert "Projects/2024/ClientB" in text
        assert "Projects/Archive" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_empty_namespace(self, mock_logseq_class):
        """Test namespace tree with no pages."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_pages_tree_from_namespace.return_value = []
        mock_logseq_class.return_value = mock_api

        handler = GetPagesTreeFromNamespaceToolHandler()
        result = handler.run_tool({"namespace": "EmptyNamespace"})

        # Verify result
        text = result[0].text
        assert "No pages found in namespace 'EmptyNamespace'" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_missing_args(self):
        """Test tool with missing namespace argument."""
        handler = GetPagesTreeFromNamespaceToolHandler()

        with pytest.raises(RuntimeError, match="namespace argument required"):
            handler.run_tool({})


class TestRenamePageToolHandler:
    """Test cases for RenamePageToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = RenamePageToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "rename_page"
        assert "rename" in tool.description.lower()
        assert "old_name" in tool.inputSchema["properties"]
        assert "new_name" in tool.inputSchema["properties"]
        assert "old_name" in tool.inputSchema["required"]
        assert "new_name" in tool.inputSchema["required"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful page rename."""
        # Setup mock
        mock_api = Mock()
        mock_api.rename_page.return_value = None
        mock_logseq_class.return_value = mock_api

        handler = RenamePageToolHandler()
        result = handler.run_tool({"old_name": "OldPage", "new_name": "NewPage"})

        # Verify API was called correctly
        mock_api.rename_page.assert_called_once_with("OldPage", "NewPage")

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        text = result[0].text
        assert "Successfully renamed" in text
        assert "OldPage" in text
        assert "NewPage" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_source_not_found(self, mock_logseq_class):
        """Test rename with non-existent source page."""
        # Setup mock to raise ValueError
        mock_api = Mock()
        mock_api.rename_page.side_effect = ValueError("Page 'NonExistent' does not exist")
        mock_logseq_class.return_value = mock_api

        handler = RenamePageToolHandler()
        result = handler.run_tool({"old_name": "NonExistent", "new_name": "NewPage"})

        # Verify error message
        text = result[0].text
        assert "does not exist" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_target_exists(self, mock_logseq_class):
        """Test rename to existing page name."""
        # Setup mock to raise ValueError
        mock_api = Mock()
        mock_api.rename_page.side_effect = ValueError("Page 'ExistingPage' already exists")
        mock_logseq_class.return_value = mock_api

        handler = RenamePageToolHandler()
        result = handler.run_tool({"old_name": "OldPage", "new_name": "ExistingPage"})

        # Verify error message
        text = result[0].text
        assert "already exists" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_missing_args(self):
        """Test tool with missing arguments."""
        handler = RenamePageToolHandler()

        with pytest.raises(RuntimeError, match="old_name and new_name arguments required"):
            handler.run_tool({"old_name": "OnlyOld"})


class TestGetPageBacklinksToolHandler:
    """Test cases for GetPageBacklinksToolHandler."""

    def test_get_tool_description(self):
        """Test tool description schema."""
        handler = GetPageBacklinksToolHandler()
        tool = handler.get_tool_description()

        assert tool.name == "get_page_backlinks"
        assert "backlink" in tool.description.lower()
        assert "page_name" in tool.inputSchema["properties"]
        assert "include_content" in tool.inputSchema["properties"]
        assert "page_name" in tool.inputSchema["required"]

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_success(self, mock_logseq_class):
        """Test successful backlinks retrieval."""
        # Setup mock with backlinks data
        mock_api = Mock()
        mock_api.get_page_linked_references.return_value = [
            [
                {"originalName": "Dec 15th, 2024"},
                [
                    {"content": "session [[Customer/Orienteme]]"},
                    {"content": "followup with [[Customer/Orienteme]] team"}
                ]
            ],
            [
                {"originalName": "Projects/AI Consulting"},
                [
                    {"content": "Active client: [[Customer/Orienteme]]"}
                ]
            ]
        ]
        mock_logseq_class.return_value = mock_api

        handler = GetPageBacklinksToolHandler()
        result = handler.run_tool({"page_name": "Customer/Orienteme"})

        # Verify API was called correctly
        mock_api.get_page_linked_references.assert_called_once_with("Customer/Orienteme")

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        text = result[0].text
        assert "Dec 15th, 2024" in text
        assert "Projects/AI Consulting" in text
        assert "2 references" in text
        assert "1 reference" in text
        assert "Total: 2 pages, 3 references" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_no_backlinks(self, mock_logseq_class):
        """Test page with no backlinks."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_page_linked_references.return_value = []
        mock_logseq_class.return_value = mock_api

        handler = GetPageBacklinksToolHandler()
        result = handler.run_tool({"page_name": "OrphanPage"})

        # Verify result
        text = result[0].text
        assert "No backlinks found for page 'OrphanPage'" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    @patch('mcp_logseq.tools.logseq.LogSeq')
    def test_run_tool_without_content(self, mock_logseq_class):
        """Test backlinks without including block content."""
        # Setup mock
        mock_api = Mock()
        mock_api.get_page_linked_references.return_value = [
            [
                {"originalName": "Source Page"},
                [{"content": "Reference to [[Target]]"}]
            ]
        ]
        mock_logseq_class.return_value = mock_api

        handler = GetPageBacklinksToolHandler()
        result = handler.run_tool({"page_name": "Target", "include_content": False})

        # Verify result shows page but not detailed content
        text = result[0].text
        assert "Source Page" in text
        assert "1 reference" in text

    @patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
    def test_run_tool_missing_args(self):
        """Test tool with missing page_name argument."""
        handler = GetPageBacklinksToolHandler()

        with pytest.raises(RuntimeError, match="page_name argument required"):
            handler.run_tool({})