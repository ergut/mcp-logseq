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
        assert client.protocol == "http"
        assert client.host == "127.0.0.1"
        assert client.port == 12315
        assert client.verify_ssl == False
        assert client.timeout == (3, 6)

    def test_init_with_custom_params(self, mock_api_key):
        """Test LogSeq client initialization with custom parameters."""
        client = LogSeq(
            api_key=mock_api_key,
            protocol="https",
            host="localhost",
            port=8080,
            verify_ssl=True,
        )

        assert client.api_key == mock_api_key
        assert client.protocol == "https"
        assert client.host == "localhost"
        assert client.port == 8080
        assert client.verify_ssl == True

    def test_get_base_url(self, logseq_client):
        """Test base URL generation."""
        url = logseq_client.get_base_url()
        assert url == "http://127.0.0.1:12315/api"

    def test_get_headers(self, logseq_client):
        """Test authentication headers generation."""
        headers = logseq_client._get_headers()
        expected = {"Authorization": f"Bearer {logseq_client.api_key}"}
        assert headers == expected

    @responses.activate
    def test_create_page_success(self, logseq_client, mock_logseq_responses):
        """Test successful page creation."""
        # Mock the createPage API call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["create_page_success"],
            status=200,
        )

        result = logseq_client.create_page("Test Page", "")
        assert result == mock_logseq_responses["create_page_success"]

        # Verify the request
        assert len(responses.calls) == 1
        body = responses.calls[0].request.body
        assert body is not None
        request_data = json.loads(body)
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
            status=200,
        )

        # Mock appendBlockInPage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200,
        )

        result = logseq_client.create_page("Test Page", "Test content")
        assert result == mock_logseq_responses["create_page_success"]

        # Verify both API calls were made
        assert len(responses.calls) == 2

        # Check appendBlockInPage call
        body = responses.calls[1].request.body
        assert body is not None
        append_request = json.loads(body)
        assert append_request["method"] == "logseq.Editor.appendBlockInPage"
        assert append_request["args"] == ["Test Page", "Test content"]

    @responses.activate
    def test_create_page_network_error(self, logseq_client):
        """Test page creation with network error."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body=requests.exceptions.ConnectionError("Connection failed"),
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
            status=200,
        )

        result = logseq_client.list_pages()
        assert result == mock_logseq_responses["list_pages_success"]

        # Verify the request
        body = responses.calls[0].request.body
        assert body is not None
        request_data = json.loads(body)
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
            status=200,
        )

        # Mock getPageBlocksTree call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["get_page_blocks_success"],
            status=200,
        )

        result = logseq_client.get_page_content("Test Page")

        # Properties are extracted from the first block
        first_block_props = mock_logseq_responses["get_page_blocks_success"][0].get(
            "properties", {}
        )
        expected = {
            "page": {
                **mock_logseq_responses["get_page_success"],
                "properties": first_block_props,
            },
            "blocks": mock_logseq_responses["get_page_blocks_success"],
        }
        assert result == expected

        # Verify only two API calls were made (getPage and getPageBlocksTree)
        assert len(responses.calls) == 2

    @responses.activate
    def test_get_page_content_not_found(self, logseq_client):
        """Test page content retrieval for non-existent page."""
        # Mock getPage returning None/null
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body="null",
            status=200,
            content_type="application/json",
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
            status=200,
        )

        # Mock deletePage call
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"success": True},
            status=200,
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
            status=200,
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
            status=200,
        )

        result = logseq_client.search_content("test query")
        assert result == mock_logseq_responses["search_success"]

        # Verify the request
        body = responses.calls[0].request.body
        assert body is not None
        request_data = json.loads(body)
        assert request_data["method"] == "logseq.search"
        assert request_data["args"] == ["test query", {}]

    @responses.activate
    def test_search_content_with_options(self, logseq_client, mock_logseq_responses):
        """Test content search with custom options."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["search_success"],
            status=200,
        )

        options = {"limit": 10}
        result = logseq_client.search_content("test query", options)
        assert result == mock_logseq_responses["search_success"]

        # Verify the request includes options
        body = responses.calls[0].request.body
        assert body is not None
        request_data = json.loads(body)
        assert request_data["args"] == ["test query", options]
