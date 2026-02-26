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

    def _add_create_mocks(self, page_json=None):
        """Register the 4 HTTP mocks needed for a create_page_with_blocks call with blocks."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=page_json or {"uuid": "page-uuid", "name": "Test Page"}, status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": ""}], status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock

    @responses.activate
    def test_create_page_with_properties_passes_to_create_page(self, logseq_client):
        """Properties are passed as the 2nd arg to createPage (page entity level)."""
        self._add_create_mocks()

        properties = {"priority": "high", "status": "active"}
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        # Properties are in the 2nd arg — page entity level, not block level
        assert body["args"][1] == {"priority": "high", "status": "active"}
        assert body["args"][2] == {"createFirstBlock": True}

        # upsertBlockProperty must NOT be called — that would make them block-level
        upsert_calls = [
            call for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 0

    @responses.activate
    def test_create_page_without_properties(self, logseq_client):
        """Creating a page without properties passes an empty dict to createPage."""
        self._add_create_mocks()

        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties=None)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        assert body["args"][1] == {}  # empty dict when no properties

        upsert_calls = [
            call for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 0

    @responses.activate
    def test_create_page_with_list_properties(self, logseq_client):
        """List-type properties (e.g. tags) are passed directly in the createPage call."""
        self._add_create_mocks()

        properties = {"tags": ["project", "urgent", "backend"]}
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        assert body["args"][1]["tags"] == ["project", "urgent", "backend"]


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

        # Mock getPage for _get_page_level_properties (returns existing page-level props)
        responses.add(
            responses.POST,
            "http://127.0.0.1:12315/api",
            json={"name": "Test Page", "properties": {"priority": "low", "status": "old"}},
            status=200,
        )

        # Mock setPageProperties for _set_page_level_properties
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

        # Verify setPageProperties was called (page-level, not block-level)
        import json
        set_props_calls = [
            call for call in responses.calls
            if "setPageProperties" in str(call.request.body)
        ]
        assert len(set_props_calls) == 1
        body = json.loads(set_props_calls[0].request.body)
        assert body["method"] == "logseq.Editor.setPageProperties"
        assert body["args"][0] == "Test Page"

        # Verify upsertBlockProperty was NOT called (would be block-level)
        upsert_calls = [
            call for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 0

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

        # Mock setPageProperties for _set_page_level_properties
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

        # Verify setPageProperties was called (page-level, not block-level)
        import json
        set_props_calls = [
            call for call in responses.calls
            if "setPageProperties" in str(call.request.body)
        ]
        assert len(set_props_calls) == 1
        body = json.loads(set_props_calls[0].request.body)
        assert body["method"] == "logseq.Editor.setPageProperties"

        # Verify upsertBlockProperty was NOT called
        upsert_calls = [
            call for call in responses.calls
            if "upsertBlockProperty" in str(call.request.body)
        ]
        assert len(upsert_calls) == 0

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
    """Test that various property value types are correctly passed to createPage."""

    def _add_create_mocks(self):
        """Register the 4 HTTP mocks needed for a create_page_with_blocks call with blocks."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json={"uuid": "page-uuid"}, status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-1"}], status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock

    @responses.activate
    def test_string_properties(self, logseq_client):
        """String properties are passed verbatim in the createPage call."""
        self._add_create_mocks()

        properties = {"title": "My Title", "author": "John Doe"}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["args"][1] == {"title": "My Title", "author": "John Doe"}

    @responses.activate
    def test_number_properties(self, logseq_client):
        """Numeric properties are passed verbatim in the createPage call."""
        self._add_create_mocks()

        properties = {"priority": 5, "score": 9.5}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["args"][1]["priority"] == 5
        assert body["args"][1]["score"] == 9.5

    @responses.activate
    def test_nested_properties(self, logseq_client):
        """Nested dict properties are passed verbatim in the createPage call."""
        self._add_create_mocks()

        properties = {"metadata": {"author": "John", "date": "2024-01-01"}}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["args"][1]["metadata"] == {"author": "John", "date": "2024-01-01"}


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
        """End-to-end: tags dict is normalized to an array in the createPage call."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json={"uuid": "page-uuid"}, status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-1"}], status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock

        properties = {"tags": {"hello": True, "test": True}}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        # Normalized to a list, not the raw dict
        assert isinstance(body["args"][1]["tags"], list)
        assert set(body["args"][1]["tags"]) == {"hello", "test"}
