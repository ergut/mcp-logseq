"""
Tests for page property persistence in LogSeq API.

These tests verify that page properties are correctly stored and retrieved
through the LogSeq HTTP API, focusing on the proper handling of properties
on the first block of a page.
"""

import responses
import pytest
from mcp_logseq.logseq import LogSeq


class TestCreatePageProperties:
    """Test property persistence during page creation."""

    @responses.activate
    def test_create_page_with_properties_calls_upsert(self, logseq_client):
        """Test that creating a page with properties calls upsertBlockProperty."""
        # Mock createPage (without properties)
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid", "name": "Test Page"},
            status=200,
        )

        # Mock getPageBlocksTree for getting first block
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "First block"}],
            status=200,
        )

        # Mock insertBatchBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )

        # Mock removeBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Mock getPageBlocksTree for property update
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2", "content": "Content"}],
            status=200,
        )

        # Mock upsertBlockProperty calls (one for each property)
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Create page with properties
        properties = {"priority": "high", "status": "active"}
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties)

        # Verify the createPage call does NOT include properties
        create_page_call = responses.calls[0]
        assert create_page_call.request.body is not None
        import json

        body = json.loads(create_page_call.request.body)
        assert body["method"] == "logseq.Editor.createPage"
        # Second arg should be empty dict (no properties)
        assert body["args"][1] == {}

        # Verify upsertBlockProperty was called for each property
        upsert_calls = [
            call
            for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 2

    @responses.activate
    def test_create_page_without_properties(self, logseq_client):
        """Test that creating a page without properties works correctly."""
        # Mock createPage
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid", "name": "Test Page"},
            status=200,
        )

        # Mock getPageBlocksTree
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "First block"}],
            status=200,
        )

        # Mock insertBatchBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )

        # Mock removeBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Create page without properties
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties=None)

        # Verify no upsertBlockProperty calls were made
        upsert_calls = [
            call
            for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 0

    @responses.activate
    def test_create_page_with_list_properties(self, logseq_client):
        """Test creating a page with list-type properties (e.g., tags)."""
        # Mock createPage
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid", "name": "Test Page"},
            status=200,
        )

        # Mock getPageBlocksTree for getting first block
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "First block"}],
            status=200,
        )

        # Mock insertBatchBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )

        # Mock removeBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Mock getPageBlocksTree for property update
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2", "content": "Content"}],
            status=200,
        )

        # Mock upsertBlockProperty
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Create page with list property
        properties = {"tags": ["project", "urgent", "backend"]}
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties)

        # Verify upsertBlockProperty was called with list value
        import json

        upsert_call = next(
            call
            for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        )
        assert upsert_call.request.body is not None
        body = json.loads(upsert_call.request.body)
        assert body["args"][1] == "tags"
        assert body["args"][2] == ["project", "urgent", "backend"]


class TestUpdatePageProperties:
    """Test property persistence during page updates."""

    @responses.activate
    def test_update_page_append_mode_merges_properties(self, logseq_client):
        """Test that append mode merges new properties with existing ones."""
        # Mock list_pages for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"name": "Test Page", "originalName": "Test Page"}],
            status=200,
        )

        # Mock getPageBlocksTree for getting last block
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {
                    "uuid": "block-1",
                    "content": "Existing",
                    "properties": {"priority": "low"},
                }
            ],
            status=200,
        )

        # Mock insertBatchBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )

        # Mock getPageBlocksTree for getting existing properties
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {
                    "uuid": "block-1",
                    "content": "Existing",
                    "properties": {"priority": "low", "status": "old"},
                }
            ],
            status=200,
        )

        # Mock getPageBlocksTree for property update
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "Existing", "properties": {}}],
            status=200,
        )

        # Mock upsertBlockProperty calls (for merged properties)
        for _ in range(3):  # priority, status, tags
            responses.add(
                responses.POST,
                "http://127.0.0.1:12315/api",
                json=True,
                status=200,
            )

        # Update with new properties in append mode
        new_properties = {"priority": "high", "tags": ["urgent"]}
        blocks = [{"content": "New content"}]
        result = logseq_client.update_page_with_blocks(
            "Test Page", blocks, properties=new_properties, mode="append"
        )

        # Verify properties were merged
        updates = dict(result["updates"])
        merged_props = updates["properties"]
        assert merged_props["priority"] == "high"  # Overwritten
        assert merged_props["status"] == "old"  # Preserved
        assert merged_props["tags"] == ["urgent"]  # Added

    @responses.activate
    def test_update_page_replace_mode_replaces_properties(self, logseq_client):
        """Test that replace mode replaces all properties."""
        # Mock list_pages for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"name": "Test Page", "originalName": "Test Page"}],
            status=200,
        )

        # Mock getPageBlocksTree for clearing
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {
                    "uuid": "block-1",
                    "content": "Old",
                    "properties": {"priority": "low", "status": "old"},
                }
            ],
            status=200,
        )

        # Mock removeBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Mock appendBlockInPage
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "block-2", "content": "New"},
            status=200,
        )

        # Mock getPageBlocksTree for property update
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2", "content": "New", "properties": {}}],
            status=200,
        )

        # Mock upsertBlockProperty calls (only new properties)
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=True,
            status=200,
        )

        # Update with new properties in replace mode
        new_properties = {"priority": "high"}
        blocks = [{"content": "New content"}]
        result = logseq_client.update_page_with_blocks(
            "Test Page", blocks, properties=new_properties, mode="replace"
        )

        # Verify only new properties are set (no merge)
        updates = dict(result["updates"])
        assert updates["properties"] == {"priority": "high"}
        assert "status" not in updates["properties"]

    @responses.activate
    def test_update_page_with_empty_properties_dict(self, logseq_client):
        """Test that empty properties dict doesn't cause errors."""
        # Mock list_pages for validation
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"name": "Test Page", "originalName": "Test Page"}],
            status=200,
        )

        # Mock getPageBlocksTree
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "Existing"}],
            status=200,
        )

        # Mock insertBatchBlock
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )

        # Update with empty properties dict
        blocks = [{"content": "New content"}]
        result = logseq_client.update_page_with_blocks(
            "Test Page", blocks, properties={}, mode="append"
        )

        # Verify no property updates in results
        updates = dict(result.get("updates", []))
        assert "properties" not in updates


class TestPropertyTypes:
    """Test various property value types."""

    @responses.activate
    def test_string_properties(self, logseq_client):
        """Test simple string properties."""
        # Setup mocks for create
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1"}],
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )

        properties = {"title": "My Title", "author": "John Doe"}
        logseq_client.create_page_with_blocks(
            "Test", [{"content": "Content"}], properties
        )

        # Verify string values passed correctly
        import json

        upsert_calls = [
            call
            for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 2

    @responses.activate
    def test_number_properties(self, logseq_client):
        """Test numeric properties."""
        # Setup mocks
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1"}],
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )

        properties = {"priority": 5, "score": 9.5}
        logseq_client.create_page_with_blocks(
            "Test", [{"content": "Content"}], properties
        )

        # Verify numeric values passed correctly
        import json

        upsert_calls = [
            call
            for call in responses.calls
            if call.request.body is not None
            and "upsertBlockProperty" in str(call.request.body)
        ]
        bodies = [
            json.loads(call.request.body)
            for call in upsert_calls
            if call.request.body is not None
        ]
        values = [body["args"][2] for body in bodies]
        assert 5 in values
        assert 9.5 in values

    @responses.activate
    def test_nested_properties(self, logseq_client):
        """Test nested/complex properties."""
        # Setup mocks
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1"}],
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )

        properties = {"metadata": {"author": "John", "date": "2024-01-01"}}
        logseq_client.create_page_with_blocks(
            "Test", [{"content": "Content"}], properties
        )

        # Verify nested object passed correctly
        import json

        upsert_calls = [
            call
            for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 1
        assert upsert_calls[0].request.body is not None
        body = json.loads(upsert_calls[0].request.body)
        assert body["args"][1] == "metadata"
        assert isinstance(body["args"][2], dict)


class TestGetPageProperties:
    """Test retrieving page properties."""

    @responses.activate
    def test_get_page_properties_helper(self, logseq_client):
        """Test the _get_page_properties helper method."""
        # Mock getPageBlocksTree
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[
                {
                    "uuid": "block-1",
                    "content": "First block",
                    "properties": {"priority": "high", "tags": ["test"]},
                }
            ],
            status=200,
        )

        properties = logseq_client._get_page_properties("Test Page")
        assert properties == {"priority": "high", "tags": ["test"]}

    @responses.activate
    def test_get_page_properties_empty_page(self, logseq_client):
        """Test getting properties from page with no blocks."""
        # Mock getPageBlocksTree returning empty list
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[],
            status=200,
        )

        properties = logseq_client._get_page_properties("Empty Page")
        assert properties == {}

    @responses.activate
    def test_get_page_properties_no_properties(self, logseq_client):
        """Test getting properties from page with blocks but no properties."""
        # Mock getPageBlocksTree
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1", "content": "First block"}],
            status=200,
        )

        properties = logseq_client._get_page_properties("Test Page")
        assert properties == {}


class TestPropertyValueNormalization:
    """Test property value normalization for Logseq compatibility."""

    def test_normalize_tags_dict_to_array(self, logseq_client):
        """Test that tags as dict with boolean values are converted to array."""
        # Input: {"hello": true, "test": true}
        # Expected output: ["hello", "test"]
        result = logseq_client._normalize_property_value(
            "tags", {"hello": True, "test": True}
        )
        assert isinstance(result, list)
        assert set(result) == {"hello", "test"}

    def test_normalize_tags_dict_filters_false_values(self, logseq_client):
        """Test that tags dict filters out false values."""
        # Input: {"keep": true, "remove": false}
        # Expected output: ["keep"]
        result = logseq_client._normalize_property_value(
            "tags", {"keep": True, "remove": False}
        )
        assert result == ["keep"]

    def test_normalize_tags_array_unchanged(self, logseq_client):
        """Test that tags as array remain unchanged."""
        # Input: ["tag1", "tag2"]
        # Expected output: ["tag1", "tag2"]
        result = logseq_client._normalize_property_value("tags", ["tag1", "tag2"])
        assert result == ["tag1", "tag2"]

    def test_normalize_aliases_dict_to_array(self, logseq_client):
        """Test that aliases property is handled like tags."""
        result = logseq_client._normalize_property_value(
            "aliases", {"alias1": True, "alias2": True}
        )
        assert isinstance(result, list)
        assert set(result) == {"alias1", "alias2"}

    def test_normalize_alias_singular_dict_to_array(self, logseq_client):
        """Test that alias (singular) property is handled like tags."""
        result = logseq_client._normalize_property_value("alias", {"myalias": True})
        assert result == ["myalias"]

    def test_normalize_other_property_dict_unchanged(self, logseq_client):
        """Test that non-tags dicts remain unchanged (for nested properties)."""
        # Input: {"author": "John", "date": "2024"}
        # Expected output: unchanged (not a tags property)
        metadata = {"author": "John", "date": "2024"}
        result = logseq_client._normalize_property_value("metadata", metadata)
        assert result == metadata

    def test_normalize_string_value_unchanged(self, logseq_client):
        """Test that string values remain unchanged."""
        result = logseq_client._normalize_property_value("title", "My Title")
        assert result == "My Title"

    def test_normalize_number_value_unchanged(self, logseq_client):
        """Test that number values remain unchanged."""
        result = logseq_client._normalize_property_value("priority", 5)
        assert result == 5

    def test_normalize_empty_tags_dict(self, logseq_client):
        """Test that empty tags dict returns empty array."""
        result = logseq_client._normalize_property_value("tags", {})
        assert result == []

    @responses.activate
    def test_create_page_with_tags_dict_normalizes(self, logseq_client):
        """Test end-to-end: creating page with tags dict converts to array."""
        # Setup mocks
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"uuid": "page-uuid"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-1"}],
            status=200,
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json=[{"uuid": "block-2"}],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api", json=True, status=200
        )

        # Create page with tags as dict (like the user reported)
        properties = {"tags": {"hello": True, "test": True}}
        logseq_client.create_page_with_blocks(
            "Test", [{"content": "Content"}], properties
        )

        # Find the upsertBlockProperty call
        import json

        upsert_calls = [
            call
            for call in responses.calls
            if call.request.body is not None
            and "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 1

        # Verify the value passed is an array, not a dict
        assert upsert_calls[0].request.body is not None
        body = json.loads(upsert_calls[0].request.body)
        assert body["args"][1] == "tags"
        assert isinstance(body["args"][2], list)
        assert set(body["args"][2]) == {"hello", "test"}
