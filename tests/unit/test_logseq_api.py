import json
import pytest
import responses
import requests
from unittest.mock import patch
from mcp_logseq.logseq import LogSeq

class TestLogSeqAPI:
    """Test cases for the LogSeq API client."""

    def test_init_with_defaults(self, mock_api_key):
        """Test LogSeq client initialization with default parameters."""
        client = LogSeq(api_key=mock_api_key)
        
        assert client.api_key == mock_api_key
        assert client.protocol == 'http'
        assert client.host == "127.0.0.1"
        assert client.port == 12315
        assert client.verify_ssl == False
        assert client.timeout == (3, 6)

    def test_init_with_custom_params(self, mock_api_key):
        """Test LogSeq client initialization with custom parameters."""
        client = LogSeq(
            api_key=mock_api_key,
            protocol='https',
            host='localhost',
            port=8080,
            verify_ssl=True
        )
        
        assert client.api_key == mock_api_key
        assert client.protocol == 'https'
        assert client.host == 'localhost'
        assert client.port == 8080
        assert client.verify_ssl == True

    def test_get_base_url(self, logseq_client):
        """Test base URL generation."""
        url = logseq_client.get_base_url()
        assert url == "http://127.0.0.1:12315/api"

    def test_get_headers(self, logseq_client):
        """Test authentication headers generation."""
        headers = logseq_client._get_headers()
        expected = {'Authorization': f'Bearer {logseq_client.api_key}'}
        assert headers == expected

    @responses.activate
    def test_create_page_success(self, logseq_client, mock_logseq_responses):
        """Test successful page creation."""
        # Mock the createPage API call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["create_page_success"],
            status=200
        )
        
        result = logseq_client.create_page("Test Page", "")
        assert result == mock_logseq_responses["create_page_success"]
        
        # Verify the request
        assert len(responses.calls) == 1
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.createPage"
        assert request_data["args"] == ["Test Page", {}, {"createFirstBlock": True}]

    @responses.activate
    def test_create_page_with_content(self, logseq_client, mock_logseq_responses):
        """Test page creation with content."""
        # Mock createPage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["create_page_success"],
            status=200
        )
        
        # Mock appendBlockInPage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200
        )
        
        result = logseq_client.create_page("Test Page", "Test content")
        assert result == mock_logseq_responses["create_page_success"]
        
        # Verify both API calls were made
        assert len(responses.calls) == 2
        
        # Check appendBlockInPage call
        append_request = json.loads(responses.calls[1].request.body)
        assert append_request["method"] == "logseq.Editor.appendBlockInPage"
        assert append_request["args"] == ["Test Page", "Test content"]

    @responses.activate
    def test_create_page_network_error(self, logseq_client):
        """Test page creation with network error."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body=requests.exceptions.ConnectionError("Connection failed")
        )
        
        with pytest.raises(requests.exceptions.ConnectionError):
            logseq_client.create_page("Test Page", "")

    @responses.activate
    def test_list_pages_success(self, logseq_client, mock_logseq_responses):
        """Test successful page listing."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["list_pages_success"],
            status=200
        )
        
        result = logseq_client.list_pages()
        assert result == mock_logseq_responses["list_pages_success"]
        
        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.getAllPages"
        assert request_data["args"] == []

    @responses.activate
    def test_get_page_content_success(self, logseq_client, mock_logseq_responses):
        """Test successful page content retrieval."""
        # Mock getPage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_page_success"],
            status=200
        )
        
        # Mock getPageBlocksTree call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_page_blocks_success"],
            status=200
        )
        
        # Mock getPageProperties call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_page_properties_success"],
            status=200
        )
        
        result = logseq_client.get_page_content("Test Page")
        
        expected = {
            "page": {
                **mock_logseq_responses["get_page_success"],
                "properties": mock_logseq_responses["get_page_properties_success"]
            },
            "blocks": mock_logseq_responses["get_page_blocks_success"]
        }
        assert result == expected
        
        # Verify all three API calls were made
        assert len(responses.calls) == 3

    @responses.activate 
    def test_get_page_content_not_found(self, logseq_client):
        """Test page content retrieval for non-existent page."""
        # Mock getPage returning None/null
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body='null',
            status=200,
            content_type='application/json'
        )
        
        result = logseq_client.get_page_content("Non-existent Page")
        assert result is None

    @responses.activate
    def test_delete_page_success(self, logseq_client, mock_logseq_responses):
        """Test successful page deletion."""
        # Mock list_pages call for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["list_pages_success"],
            status=200
        )
        
        # Mock deletePage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200
        )
        
        result = logseq_client.delete_page("Page One")
        assert result == {"success": True}
        
        # Verify both calls were made
        assert len(responses.calls) == 2

    @responses.activate
    def test_delete_page_not_found(self, logseq_client, mock_logseq_responses):
        """Test deletion of non-existent page."""
        # Mock list_pages call for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["list_pages_success"],
            status=200
        )
        
        with pytest.raises(ValueError, match="Page 'Non-existent' does not exist"):
            logseq_client.delete_page("Non-existent")

    @responses.activate
    def test_search_content_success(self, logseq_client, mock_logseq_responses):
        """Test successful content search."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["search_success"],
            status=200
        )
        
        result = logseq_client.search_content("test query")
        assert result == mock_logseq_responses["search_success"]
        
        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.search"
        assert request_data["args"] == ["test query", {}]

    @responses.activate
    def test_search_content_with_options(self, logseq_client, mock_logseq_responses):
        """Test content search with custom options."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["search_success"],
            status=200
        )
        
        options = {"limit": 10}
        result = logseq_client.search_content("test query", options)
        assert result == mock_logseq_responses["search_success"]
        
        # Verify the request includes options
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["args"] == ["test query", options]

    @responses.activate
    def test_update_page_success(self, logseq_client, mock_logseq_responses):
        """Test successful page update."""
        # Mock list_pages call for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["list_pages_success"],
            status=200
        )
        
        # Mock updatePage call for properties
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200
        )
        
        # Mock appendBlockInPage call for content
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200
        )
        
        properties = {"priority": "high"}
        content = "New content"
        
        result = logseq_client.update_page("Page One", content=content, properties=properties)
        
        expected = {
            "updates": [("properties", {"success": True}), ("content", {"success": True})],
            "page": "Page One"
        }
        assert result == expected
        
        # Verify all calls were made
        assert len(responses.calls) == 3

    @responses.activate
    def test_get_pages_from_namespace_success(self, logseq_client, mock_logseq_responses):
        """Test successful namespace pages retrieval."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_pages_from_namespace_success"],
            status=200
        )

        result = logseq_client.get_pages_from_namespace("Customer")
        assert result == mock_logseq_responses["get_pages_from_namespace_success"]

        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.getPagesFromNamespace"
        assert request_data["args"] == ["Customer"]

    @responses.activate
    def test_get_pages_from_namespace_empty(self, logseq_client):
        """Test namespace pages retrieval with no results."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[],
            status=200
        )

        result = logseq_client.get_pages_from_namespace("EmptyNamespace")
        assert result == []

    @responses.activate
    def test_get_pages_tree_from_namespace_success(self, logseq_client, mock_logseq_responses):
        """Test successful namespace tree retrieval."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_pages_tree_from_namespace_success"],
            status=200
        )

        result = logseq_client.get_pages_tree_from_namespace("Projects")
        assert result == mock_logseq_responses["get_pages_tree_from_namespace_success"]

        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.getPagesTreeFromNamespace"
        assert request_data["args"] == ["Projects"]

    @responses.activate
    def test_get_pages_tree_from_namespace_empty(self, logseq_client):
        """Test namespace tree retrieval with no results."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[],
            status=200
        )

        result = logseq_client.get_pages_tree_from_namespace("EmptyNamespace")
        assert result == []

    @responses.activate
    def test_rename_page_success(self, logseq_client, mock_logseq_responses):
        """Test successful page rename."""
        # Mock list_pages for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {"originalName": "OldPage"},
                {"originalName": "OtherPage"}
            ],
            status=200
        )

        # Mock rename call (returns null on success)
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body='null',
            status=200,
            content_type='application/json'
        )

        result = logseq_client.rename_page("OldPage", "NewPage")
        assert result is None

        # Verify the rename request
        request_data = json.loads(responses.calls[1].request.body)
        assert request_data["method"] == "logseq.Editor.renamePage"
        assert request_data["args"] == ["OldPage", "NewPage"]

    @responses.activate
    def test_rename_page_source_not_found(self, logseq_client):
        """Test rename with non-existent source page."""
        # Mock list_pages - source doesn't exist
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {"originalName": "OtherPage"}
            ],
            status=200
        )

        with pytest.raises(ValueError, match="does not exist"):
            logseq_client.rename_page("NonExistent", "NewPage")

    @responses.activate
    def test_rename_page_target_exists(self, logseq_client):
        """Test rename to existing page name."""
        # Mock list_pages - target already exists
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {"originalName": "OldPage"},
                {"originalName": "ExistingPage"}
            ],
            status=200
        )

        with pytest.raises(ValueError, match="already exists"):
            logseq_client.rename_page("OldPage", "ExistingPage")

    @responses.activate
    def test_get_page_linked_references_success(self, logseq_client, mock_logseq_responses):
        """Test successful backlinks retrieval."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_page_linked_references_success"],
            status=200
        )

        result = logseq_client.get_page_linked_references("Customer/Orienteme")
        assert result == mock_logseq_responses["get_page_linked_references_success"]

        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.getPageLinkedReferences"
        assert request_data["args"] == ["Customer/Orienteme"]

    @responses.activate
    def test_get_page_linked_references_empty(self, logseq_client):
        """Test backlinks retrieval with no results."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[],
            status=200
        )

        result = logseq_client.get_page_linked_references("OrphanPage")
        assert result == []