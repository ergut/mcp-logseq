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

    def _add_create_mocks(self, page_json=None, with_remove=True):
        """Register HTTP mocks for a create_page_with_blocks call with blocks."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=page_json or {"uuid": "page-uuid", "name": "Test Page"}, status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": ""}], status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)
        if with_remove:
            responses.add(responses.POST, url, json=True, status=200)  # removeBlock

    @responses.activate
    def test_create_page_with_properties_passes_to_create_page(self, logseq_client):
        """Properties are passed as the 2nd arg to createPage (page entity level)."""
        self._add_create_mocks(with_remove=False)

        properties = {"priority": "high", "status": "active"}
        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        # Properties are in the 2nd arg — page entity level, not block level
        assert body["args"][1] == {"priority": "high", "status": "active"}
        assert body["args"][2] == {"createFirstBlock": True}

        # First block must NOT be removed — it holds the page properties
        remove_calls = [
            call for call in responses.calls
            if "removeBlock" in str(call.request.body)
        ]
        assert len(remove_calls) == 0

    @responses.activate
    def test_create_page_without_properties(self, logseq_client):
        """Creating a page without properties removes the empty placeholder block."""
        self._add_create_mocks(with_remove=True)

        blocks = [{"content": "Test content"}]
        logseq_client.create_page_with_blocks("Test Page", blocks, properties=None)

        import json
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        assert body["args"][1] == {}  # empty dict when no properties

        # Placeholder block must be removed when no properties
        remove_calls = [
            call for call in responses.calls
            if "removeBlock" in str(call.request.body)
        ]
        assert len(remove_calls) == 1

    @responses.activate
    def test_create_page_with_list_properties(self, logseq_client):
        """List-type properties (e.g. tags) are passed directly in the createPage call."""
        self._add_create_mocks(with_remove=False)

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
    def test_update_page_properties_only_updates_in_place(self, logseq_client):
        """
        Regression: update_page with properties-only (no content) must update
        page-level properties in-place via upsertBlockProperty on the first
        block — NOT append them as a new content block via setPageProperties.

        Sequence of expected API calls:
          1. list_pages       — page existence check
          2. getPageBlocksTree — find first block UUID for upsertBlockProperty
          3. upsertBlockProperty × N — one call per updated property key
        """
        import json

        url = "http://127.0.0.1:12315/api"

        # 1. list_pages — page exists
        responses.add(
            responses.POST, url,
            json=[{"name": "Some Page", "originalName": "Some Page"}],
            status=200,
        )

        # 2. getPageBlocksTree — returns existing blocks; first block is the
        #    page-properties pre-block
        responses.add(
            responses.POST, url,
            json=[
                {
                    "uuid": "prop-block-uuid",
                    "content": "",
                    "properties": {
                        "status": "initial",
                        "source": "human",
                        "tags": ["mcp-test"],
                    },
                },
                {
                    "uuid": "content-block-uuid",
                    "content": "This page was created to test property update behavior.",
                    "properties": {},
                },
            ],
            status=200,
        )

        # 3. upsertBlockProperty — one per updated key (status, source)
        responses.add(responses.POST, url, json=None, status=200)  # status
        responses.add(responses.POST, url, json=None, status=200)  # source

        # Call update with properties only — no content, no blocks
        logseq_client.update_page_with_blocks(
            "Some Page",
            [],
            properties={"status": "updated", "source": "ai-generated"},
            mode="append",
        )

        # Must NOT have called setPageProperties (that's the broken path that
        # appends properties as a new block body instead of updating in-place)
        set_props_calls = [
            c for c in responses.calls
            if "setPageProperties" in str(c.request.body)
        ]
        assert len(set_props_calls) == 0, (
            "setPageProperties must NOT be called — it appends properties as "
            "a block body instead of updating page-level properties in-place"
        )

        # Must NOT have called appendBlockInPage (another sign of wrong path)
        append_calls = [
            c for c in responses.calls
            if "appendBlockInPage" in str(c.request.body)
        ]
        assert len(append_calls) == 0, (
            "appendBlockInPage must NOT be called for a properties-only update"
        )

        # Must have called upsertBlockProperty for each updated key
        upsert_calls = [
            c for c in responses.calls
            if "upsertBlockProperty" in str(c.request.body)
        ]
        assert len(upsert_calls) == 2, (
            f"Expected 2 upsertBlockProperty calls (one per key), got {len(upsert_calls)}"
        )

        # Each call must target the first (properties) block
        for call in upsert_calls:
            body = json.loads(call.request.body)
            assert body["args"][0] == "prop-block-uuid", (
                "upsertBlockProperty must target the first block (the page "
                f"properties pre-block), not '{body['args'][0]}'"
            )

        # Verify the correct key/value pairs were sent
        updated = {
            json.loads(c.request.body)["args"][1]: json.loads(c.request.body)["args"][2]
            for c in upsert_calls
        }
        assert updated["status"] == "updated"
        assert updated["source"] == "ai-generated"

    @responses.activate
    def test_update_page_append_mode_merges_properties(self, logseq_client):
        """
        Append mode updates only the specified property keys via
        upsertBlockProperty, leaving unspecified keys intact on the first block.

        API call sequence:
          1. list_pages
          2. getPageBlocksTree — last block UUID for insertBatchBlock
          3. insertBatchBlock  — add the new content block
          4. getPageBlocksTree — first block UUID for upsertBlockProperty
          5. upsertBlockProperty × 2 (priority, tags)
        """
        import json

        url = "http://127.0.0.1:12315/api"

        # 1. list_pages
        responses.add(responses.POST, url,
            json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)

        # 2. getPageBlocksTree — for finding last block to insert after
        responses.add(responses.POST, url,
            json=[{"uuid": "block-1", "content": "Existing",
                   "properties": {"priority": "low", "status": "old"}}],
            status=200)

        # 3. insertBatchBlock
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)

        # 4. getPageBlocksTree — for _update_page_properties (first block UUID)
        responses.add(responses.POST, url,
            json=[{"uuid": "block-1", "content": "Existing",
                   "properties": {"priority": "low", "status": "old"}}],
            status=200)

        # 5a. upsertBlockProperty — priority
        responses.add(responses.POST, url, json=None, status=200)
        # 5b. upsertBlockProperty — tags
        responses.add(responses.POST, url, json=None, status=200)

        new_properties = {"priority": "high", "tags": ["urgent"]}
        blocks = [{"content": "New content"}]
        result = logseq_client.update_page_with_blocks(
            "Test Page", blocks, properties=new_properties, mode="append"
        )

        # Result dict contains only the supplied properties (not the full merged set)
        updates = dict(result["updates"])
        assert updates["properties"] == {"priority": "high", "tags": ["urgent"]}

        # upsertBlockProperty must be called for each supplied key (not setPageProperties)
        upsert_calls = [
            c for c in responses.calls
            if "upsertBlockProperty" in str(c.request.body)
        ]
        assert len(upsert_calls) == 2
        upserted = {
            json.loads(c.request.body)["args"][1]: json.loads(c.request.body)["args"][2]
            for c in upsert_calls
        }
        assert upserted["priority"] == "high"
        assert upserted["tags"] == ["urgent"]
        # "status" must NOT be touched — Logseq preserves it implicitly
        assert "status" not in upserted

        # setPageProperties must NOT be called
        assert not any(
            "setPageProperties" in str(c.request.body) for c in responses.calls
        )

    @responses.activate
    def test_update_page_replace_mode_replaces_properties(self, logseq_client):
        """
        Replace mode clears existing blocks, adds new content, then sets
        properties via upsertBlockProperty on the new first block.

        API call sequence:
          1. list_pages
          2. getPageBlocksTree — for clear_page_content
          3. removeBlock       — clear existing block
          4. appendBlockInPage — add first new content block
          5. getPageBlocksTree — first block UUID for upsertBlockProperty
          6. upsertBlockProperty × 1 (priority)
        """
        import json

        url = "http://127.0.0.1:12315/api"

        # 1. list_pages
        responses.add(responses.POST, url,
            json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)

        # 2. getPageBlocksTree — for clear_page_content
        responses.add(responses.POST, url,
            json=[{"uuid": "block-1", "content": "Old",
                   "properties": {"priority": "low", "status": "old"}}],
            status=200)

        # 3. removeBlock
        responses.add(responses.POST, url, json=True, status=200)

        # 4. appendBlockInPage — first new block after clearing
        responses.add(responses.POST, url,
            json={"uuid": "block-2", "content": "New content"}, status=200)

        # 5. getPageBlocksTree — for _update_page_properties (first block UUID)
        responses.add(responses.POST, url,
            json=[{"uuid": "block-2", "content": "New content", "properties": {}}],
            status=200)

        # 6. upsertBlockProperty — priority
        responses.add(responses.POST, url, json=None, status=200)

        new_properties = {"priority": "high"}
        blocks = [{"content": "New content"}]
        result = logseq_client.update_page_with_blocks(
            "Test Page", blocks, properties=new_properties, mode="replace"
        )

        # Result contains only the new properties
        updates = dict(result["updates"])
        assert updates["properties"] == {"priority": "high"}
        assert "status" not in updates["properties"]

        # upsertBlockProperty must be used — NOT setPageProperties
        upsert_calls = [
            c for c in responses.calls
            if "upsertBlockProperty" in str(c.request.body)
        ]
        assert len(upsert_calls) == 1
        body = json.loads(upsert_calls[0].request.body)
        assert body["args"][1] == "priority"
        assert body["args"][2] == "high"

        assert not any(
            "setPageProperties" in str(c.request.body) for c in responses.calls
        )

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
