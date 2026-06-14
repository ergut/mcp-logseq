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
        responses.add(responses.POST, url, body="null", status=200, content_type="application/json")  # getPage existence check
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
        body = json.loads(responses.calls[1].request.body)
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
        body = json.loads(responses.calls[1].request.body)
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
        body = json.loads(responses.calls[1].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        assert body["args"][1]["tags"] == ["project", "urgent", "backend"]


class TestUpdatePageProperties:
    """Test property persistence during page updates.

    Property storage is graph-type dependent:
      - DB graphs store page properties at the page entity level
        (setPageProperties).
      - File graphs store them as ``key:: value`` lines in the page's first
        block (upsertBlockProperty / removeBlockProperty).
    """

    @staticmethod
    def _calls_for(method):
        return [c for c in responses.calls if method in str(c.request.body)]

    # ------------------------------------------------------------------ #
    # DB graph mode                                                      #
    # ------------------------------------------------------------------ #

    @responses.activate
    def test_db_mode_append_merges_via_set_page_properties(self, logseq_client_db):
        """DB graphs: append merges with existing page-level props via setPageProperties."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": "Existing"}], status=200)  # get last block
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)  # insertBatchBlock
        responses.add(responses.POST, url, json={"name": "Test Page", "properties": {"priority": "low", "status": "old"}}, status=200)  # getPage
        responses.add(responses.POST, url, json=True, status=200)  # setPageProperties

        result = logseq_client_db.update_page_with_blocks(
            "Test Page", [{"content": "New content"}],
            properties={"priority": "high", "tags": ["urgent"]}, mode="append",
        )

        merged = dict(result["updates"])["properties"]
        assert merged["priority"] == "high"   # overwritten
        assert merged["status"] == "old"      # preserved from existing
        assert merged["tags"] == ["urgent"]   # added

        import json
        set_calls = self._calls_for("setPageProperties")
        assert len(set_calls) == 1
        body = json.loads(set_calls[0].request.body)
        assert body["args"][0] == "Test Page"
        # The full merged set is written page-level
        assert body["args"][1]["status"] == "old"
        assert self._calls_for("upsertBlockProperty") == []

    @responses.activate
    def test_db_mode_replace_uses_set_page_properties(self, logseq_client_db):
        """DB graphs: replace writes only the new props via setPageProperties."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": "Old", "properties": {"status": "old"}}], status=200)  # clear: get blocks
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock
        responses.add(responses.POST, url, json={"uuid": "block-2", "content": "New"}, status=200)  # appendBlockInPage
        responses.add(responses.POST, url, json=True, status=200)  # setPageProperties

        result = logseq_client_db.update_page_with_blocks(
            "Test Page", [{"content": "New content"}],
            properties={"priority": "high"}, mode="replace",
        )

        assert dict(result["updates"])["properties"] == {"priority": "high"}
        assert len(self._calls_for("setPageProperties")) == 1
        assert self._calls_for("upsertBlockProperty") == []

    # ------------------------------------------------------------------ #
    # File graph mode                                                    #
    # ------------------------------------------------------------------ #

    @responses.activate
    def test_file_mode_append_upserts_only_supplied_keys(self, logseq_client):
        """File graphs: append upserts supplied keys in place on the first block.

        Untouched keys survive natively (no remove calls), which is what gives
        append its merge semantics on file graphs.
        """
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": "Existing", "properties": {"priority": "low", "status": "old"}}], status=200)  # get last block
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)  # insertBatchBlock
        responses.add(responses.POST, url, json={"name": "Test Page", "properties": {"priority": "low", "status": "old"}}, status=200)  # getPage (merge bookkeeping)
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": "Existing", "properties": {"priority": "low", "status": "old"}}], status=200)  # _update_page_properties: get first block
        responses.add(responses.POST, url, json=True, status=200)  # upsertBlockProperty (repeats)

        result = logseq_client.update_page_with_blocks(
            "Test Page", [{"content": "New content"}],
            properties={"priority": "high", "tags": ["urgent"]}, mode="append",
        )

        # Result still reports the merged view for the caller
        merged = dict(result["updates"])["properties"]
        assert merged["priority"] == "high"
        assert merged["status"] == "old"
        assert merged["tags"] == ["urgent"]

        # Page properties go through the first block, NOT setPageProperties
        assert self._calls_for("setPageProperties") == []

        import json
        upsert_keys = {
            json.loads(c.request.body)["args"][1] for c in self._calls_for("upsertBlockProperty")
        }
        assert upsert_keys == {"priority", "tags"}  # only supplied keys touched
        # Untouched keys are never removed in append mode
        assert self._calls_for("removeBlockProperty") == []
        # All upserts target the first block
        for c in self._calls_for("upsertBlockProperty"):
            assert json.loads(c.request.body)["args"][0] == "block-1"

    @responses.activate
    def test_file_mode_replace_removes_stale_keys(self, logseq_client):
        """File graphs: replace removes first-block props absent from the new set."""
        url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, url, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
        responses.add(responses.POST, url, json=[{"uuid": "block-1", "content": "Old", "properties": {"priority": "low", "status": "old"}}], status=200)  # clear: get blocks
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock (clear content)
        responses.add(responses.POST, url, json={"uuid": "block-2", "content": "New"}, status=200)  # appendBlockInPage anchor
        responses.add(responses.POST, url, json=[{"uuid": "block-2", "content": "New", "properties": {"priority": "low", "status": "old"}}], status=200)  # _replace_page_properties: get first block
        responses.add(responses.POST, url, json=True, status=200)  # removeBlockProperty / upsertBlockProperty (repeats)

        result = logseq_client.update_page_with_blocks(
            "Test Page", [{"content": "New content"}],
            properties={"priority": "high"}, mode="replace",
        )

        assert dict(result["updates"])["properties"] == {"priority": "high"}
        assert self._calls_for("setPageProperties") == []

        import json
        # "status" was present but not in the new set -> removed
        removed_keys = {
            json.loads(c.request.body)["args"][1] for c in self._calls_for("removeBlockProperty")
        }
        assert removed_keys == {"status"}
        # "priority" upserted in place
        upsert_keys = {
            json.loads(c.request.body)["args"][1] for c in self._calls_for("upsertBlockProperty")
        }
        assert upsert_keys == {"priority"}

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
        responses.add(responses.POST, url, body="null", status=200, content_type="application/json")  # getPage existence check
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
        body = json.loads(responses.calls[1].request.body)
        assert body["args"][1] == {"title": "My Title", "author": "John Doe"}

    @responses.activate
    def test_number_properties(self, logseq_client):
        """Numeric properties are passed verbatim in the createPage call."""
        self._add_create_mocks()

        properties = {"priority": 5, "score": 9.5}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[1].request.body)
        assert body["args"][1]["priority"] == 5
        assert body["args"][1]["score"] == 9.5

    @responses.activate
    def test_nested_properties(self, logseq_client):
        """Nested dict properties are passed verbatim in the createPage call."""
        self._add_create_mocks()

        properties = {"metadata": {"author": "John", "date": "2024-01-01"}}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[1].request.body)
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
        responses.add(responses.POST, url, body="null", status=200, content_type="application/json")  # getPage existence check
        responses.add(responses.POST, url, json={"uuid": "page-uuid"}, status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-1"}], status=200)
        responses.add(responses.POST, url, json=[{"uuid": "block-2"}], status=200)
        responses.add(responses.POST, url, json=True, status=200)  # removeBlock

        properties = {"tags": {"hello": True, "test": True}}
        logseq_client.create_page_with_blocks("Test", [{"content": "Content"}], properties)

        import json
        body = json.loads(responses.calls[1].request.body)
        assert body["method"] == "logseq.Editor.createPage"
        # Normalized to a list, not the raw dict
        assert isinstance(body["args"][1]["tags"], list)
        assert set(body["args"][1]["tags"]) == {"hello", "test"}
