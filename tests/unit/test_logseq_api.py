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

    @responses.activate
    def test_delete_block_success(self, logseq_client):
        """Test successful block deletion calls removeBlock with the UUID."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body="null",
            status=200,
            content_type="application/json",
        )

        logseq_client.delete_block("block-uuid-abc")

        assert len(responses.calls) == 1
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.removeBlock"
        assert request_data["args"] == ["block-uuid-abc"]

    @responses.activate
    def test_delete_block_http_error(self, logseq_client):
        """Test that an HTTP error from the API propagates as an exception."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"error": "Not found"},
            status=404,
        )

        with pytest.raises(requests.exceptions.HTTPError):
            logseq_client.delete_block("block-uuid-missing")

    @responses.activate
    def test_delete_block_network_error(self, logseq_client):
        """Test that a network/connection error propagates as an exception."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        with pytest.raises(requests.exceptions.ConnectionError):
            logseq_client.delete_block("block-uuid-abc")


    @responses.activate
    def test_update_block_success(self, logseq_client):
        """Test successful block update calls updateBlock with UUID and content."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body="null",
            status=200,
            content_type="application/json",
        )

        logseq_client.update_block("block-uuid-abc", "Updated content")

        assert len(responses.calls) == 1
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.updateBlock"
        assert request_data["args"] == ["block-uuid-abc", "Updated content"]

    @responses.activate
    def test_update_block_http_error(self, logseq_client):
        """Test that an HTTP error from updateBlock propagates as an exception."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"error": "Not found"},
            status=404,
        )

        with pytest.raises(requests.exceptions.HTTPError):
            logseq_client.update_block("block-uuid-missing", "Updated")

    @responses.activate
    def test_update_block_network_error(self, logseq_client):
        """Test that a network/connection error propagates for updateBlock."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        with pytest.raises(requests.exceptions.ConnectionError):
            logseq_client.update_block("block-uuid-abc", "Updated")

    @responses.activate
    def test_query_dsl_success(self, logseq_client, mock_logseq_responses):
        """Test successful DSL query."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["query_dsl_pages_success"],
            status=200
        )

        result = logseq_client.query_dsl("(page-property type customer)")
        assert result == mock_logseq_responses["query_dsl_pages_success"]

        # Verify the request
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.DB.q"
        assert request_data["args"] == ["(page-property type customer)"]

    @responses.activate
    def test_query_dsl_empty_results(self, logseq_client, mock_logseq_responses):
        """Test DSL query with no results."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=mock_logseq_responses["query_dsl_empty"],
            status=200
        )

        result = logseq_client.query_dsl("(page-property nonexistent)")
        assert result == []

    @responses.activate
    def test_query_dsl_network_error(self, logseq_client):
        """Test DSL query with network error."""
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            body=requests.exceptions.ConnectionError("Connection failed")
        )

        with pytest.raises(requests.exceptions.ConnectionError):
            logseq_client.query_dsl("(page-property type)")
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

    @responses.activate
    def test_insert_block_as_child_success(self, logseq_client):
        """Test inserting a child block under a parent."""
        new_block = {"uuid": "child-uuid", "content": "Child content"}
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=new_block,
            status=200
        )

        result = logseq_client.insert_block_as_child("parent-uuid", "Child content")

        assert result == new_block
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["method"] == "logseq.Editor.insertBlock"
        assert request_data["args"][0] == "parent-uuid"
        assert request_data["args"][1] == "Child content"
        assert request_data["args"][2]["sibling"] is False

    @responses.activate
    def test_insert_block_as_sibling(self, logseq_client):
        """Test inserting a sibling block."""
        new_block = {"uuid": "sibling-uuid", "content": "Sibling content"}
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=new_block,
            status=200
        )

        result = logseq_client.insert_block_as_child("ref-uuid", "Sibling content", sibling=True)

        assert result == new_block
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["args"][2]["sibling"] is True

    @responses.activate
    def test_insert_block_as_child_with_properties(self, logseq_client):
        """Test inserting a child block with properties."""
        new_block = {"uuid": "todo-uuid", "content": "Task"}
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=new_block,
            status=200
        )

        result = logseq_client.insert_block_as_child(
            "parent-uuid", "Task", properties={"marker": "TODO"}
        )

        assert result == new_block
        request_data = json.loads(responses.calls[0].request.body)
        assert request_data["args"][2]["properties"] == {"marker": "TODO"}

    def test_append_block_recursive_root_level(self, logseq_client):
        """Test _append_block_recursive at root level calls append_block_in_page."""
        from unittest.mock import patch, Mock

        mock_result = {"uuid": "root-uuid"}
        with patch.object(logseq_client, "append_block_in_page", return_value=mock_result) as mock_append:
            with patch.object(logseq_client, "insert_block_as_child") as mock_insert:
                block = {"content": "Root block", "children": []}
                logseq_client._append_block_recursive("TestPage", block, parent_uuid=None)

                mock_append.assert_called_once_with("TestPage", "Root block", None)
                mock_insert.assert_not_called()

    def test_append_block_recursive_nested(self, logseq_client):
        """Test _append_block_recursive uses insert_block_as_child when parent_uuid given."""
        from unittest.mock import patch

        mock_result = {"uuid": "child-uuid"}
        with patch.object(logseq_client, "append_block_in_page") as mock_append:
            with patch.object(logseq_client, "insert_block_as_child", return_value=mock_result) as mock_insert:
                block = {"content": "Child block", "children": []}
                logseq_client._append_block_recursive("TestPage", block, parent_uuid="parent-uuid")

                mock_insert.assert_called_once_with("parent-uuid", "Child block", None)
                mock_append.assert_not_called()

    def test_append_block_recursive_with_children(self, logseq_client):
        """Test _append_block_recursive recurses into children with correct parent UUID."""
        from unittest.mock import patch, call

        call_order = []

        def fake_append(page, content, props):
            uuid = f"uuid-{content}"
            call_order.append(("append", content))
            return {"uuid": uuid}

        def fake_insert(parent_uuid, content, props):
            call_order.append(("insert", content, parent_uuid))
            return {"uuid": f"uuid-{content}"}

        with patch.object(logseq_client, "append_block_in_page", side_effect=fake_append):
            with patch.object(logseq_client, "insert_block_as_child", side_effect=fake_insert):
                block = {
                    "content": "Parent",
                    "children": [
                        {"content": "Child1", "children": []},
                        {"content": "Child2", "children": []},
                    ]
                }
                logseq_client._append_block_recursive("TestPage", block, parent_uuid=None)

        # Root block appended to page
        assert call_order[0] == ("append", "Parent")
        # Children inserted under root's uuid
        assert call_order[1] == ("insert", "Child1", "uuid-Parent")
        assert call_order[2] == ("insert", "Child2", "uuid-Parent")