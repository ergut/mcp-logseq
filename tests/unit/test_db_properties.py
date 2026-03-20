"""Tests for DB-mode property support (LOGSEQ_DB_MODE feature flag)."""

import json
import pytest
import responses
from unittest.mock import patch, Mock

from mcp_logseq.logseq import LogSeq
from mcp_logseq.tools import GetPageContentToolHandler


@pytest.fixture
def db_blocks():
    """Block tree with IDs and UUIDs as returned by getPageBlocksTree in DB-mode."""
    return [
        {
            "id": 101,
            "uuid": "uuid-block-1",
            "content": "First block",
            "properties": {},
            "children": [
                {
                    "id": 102,
                    "uuid": "uuid-block-2",
                    "content": "Child block",
                    "properties": {},
                    "children": [],
                }
            ],
        },
        {
            "id": 103,
            "uuid": "uuid-block-3",
            "content": "Second block",
            "properties": {},
            "children": [],
        },
    ]


class TestGetBlockDbProperties:
    """Tests for LogSeq.get_block_db_properties."""

    @responses.activate
    def test_happy_path(self, logseq_client):
        """Block with user properties returns resolved names and values."""
        # Query 1: get all attributes for block 101
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[":user.property/status-abc", 201], ["title", "First block"], [":db/ident", ":logseq.property/foo"]],
            status=200,
        )
        # Query 2: resolve property ident -> entity ID
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[301]],
            status=200,
        )
        # Query 3: resolve property entity title
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Status"]],
            status=200,
        )
        # Query 4: resolve value entity title (val 201 is an entity ref)
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Active"]],
            status=200,
        )

        result = logseq_client.get_block_db_properties(101)
        assert result == {"Status": "Active"}

    @responses.activate
    def test_no_user_properties(self, logseq_client):
        """Block with no :user.property/* attributes returns empty dict."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Some block"], [":db/ident", ":logseq.property/foo"]],
            status=200,
        )

        result = logseq_client.get_block_db_properties(101)
        assert result == {}

    @responses.activate
    def test_query_failure_returns_empty(self, logseq_client):
        """API failure returns empty dict instead of raising."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json={"error": "query failed"},
            status=500,
        )

        result = logseq_client.get_block_db_properties(101)
        assert result == {}

    @responses.activate
    def test_string_value_not_resolved(self, logseq_client):
        """Non-integer values are returned as strings without entity resolution."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[":user.property/notes-xyz", "plain text value"]],
            status=200,
        )
        # Resolve property ident
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[401]],
            status=200,
        )
        # Resolve property title
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Notes"]],
            status=200,
        )

        result = logseq_client.get_block_db_properties(101)
        assert result == {"Notes": "plain text value"}


class TestGetBlocksDbProperties:
    """Tests for LogSeq.get_blocks_db_properties (recursive batch)."""

    def test_processes_nested_blocks(self, logseq_client, db_blocks):
        """All blocks in tree (including children) are processed."""
        processed_ids = []

        def mock_get_props(block_id):
            processed_ids.append(block_id)
            if block_id == 101:
                return {"Status": "Active"}
            return {}

        with patch.object(logseq_client, "get_block_db_properties", side_effect=mock_get_props):
            result = logseq_client.get_blocks_db_properties(db_blocks)

        assert sorted(processed_ids) == [101, 102, 103]
        assert result == {"uuid-block-1": {"Status": "Active"}}

    def test_empty_blocks(self, logseq_client):
        """Empty block list returns empty dict."""
        result = logseq_client.get_blocks_db_properties([])
        assert result == {}


class TestResolvePropertyIdent:
    """Tests for LogSeq.resolve_property_ident."""

    @responses.activate
    def test_found(self, logseq_client):
        """Matching property name returns its ident."""
        # Query: get all idents
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[
                [501, ":user.property/status-abc"],
                [502, ":user.property/priority-def"],
                [503, ":db/ident"],
            ],
            status=200,
        )
        # Resolve title for entity 501
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Content status"]],
            status=200,
        )

        result = logseq_client.resolve_property_ident("Content status")
        assert result == ":user.property/status-abc"

    @responses.activate
    def test_case_insensitive(self, logseq_client):
        """Lookup is case-insensitive."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[501, ":user.property/status-abc"]],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Content status"]],
            status=200,
        )

        result = logseq_client.resolve_property_ident("content STATUS")
        assert result == ":user.property/status-abc"

    @responses.activate
    def test_not_found(self, logseq_client):
        """Non-existent property returns None."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[[501, ":user.property/status-abc"]],
            status=200,
        )
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            json=[["title", "Status"]],
            status=200,
        )

        result = logseq_client.resolve_property_ident("Nonexistent")
        assert result is None

    @responses.activate
    def test_query_failure(self, logseq_client):
        """API failure returns None."""
        responses.add(
            responses.POST, "http://127.0.0.1:12315/api",
            status=500,
        )

        result = logseq_client.resolve_property_ident("Status")
        assert result is None


class TestFormatBlockTreeDbMode:
    """Tests for _format_block_tree with DB-mode properties."""

    def test_db_properties_rendered_in_db_mode(self):
        """DB-mode class properties are rendered when LOGSEQ_DB_MODE=true."""
        block = {
            "content": "Test block",
            "uuid": "uuid-1",
            "properties": {},
            "children": [],
        }
        db_props = {"uuid-1": {"Status": "Active", "Priority": "High"}}

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, db_props
            )

        assert "- Test block" in lines
        assert "  Status:: Active" in lines
        assert "  Priority:: High" in lines

    def test_db_properties_not_rendered_without_flag(self):
        """DB-mode properties are NOT rendered when LOGSEQ_DB_MODE is off."""
        block = {
            "content": "Test block",
            "uuid": "uuid-1",
            "properties": {"status": "active"},
            "children": [],
        }
        db_props = {"uuid-1": {"Status": "Active"}}

        with patch("mcp_logseq.tools._db_mode", False):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, db_props
            )

        assert lines == ["- Test block"]

    def test_markdown_properties_in_content_not_duplicated(self):
        """Properties already in content are not duplicated in DB-mode."""
        block = {
            "content": "Test block\npriority:: high",
            "uuid": "uuid-1",
            "properties": {"priority": "high"},
            "children": [],
        }

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(block, 0, -1, None)

        # priority:: high is in content, should not be added again
        assert sum(1 for l in lines if "priority::" in l) == 1

    def test_logseq_internal_properties_skipped(self):
        """Properties starting with :logseq are filtered out."""
        block = {
            "content": "Test block",
            "uuid": "uuid-1",
            "properties": {":logseq.property/foo": "bar", "status": "active"},
            "children": [],
        }

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(block, 0, -1, None)

        assert any("status:: active" in l for l in lines)
        assert not any(":logseq" in l for l in lines)

    def test_nested_blocks_with_db_properties(self):
        """DB properties are rendered at correct indentation for nested blocks."""
        block = {
            "content": "Parent",
            "uuid": "uuid-parent",
            "properties": {},
            "children": [
                {
                    "content": "Child",
                    "uuid": "uuid-child",
                    "properties": {},
                    "children": [],
                }
            ],
        }
        db_props = {
            "uuid-parent": {"Type": "Project"},
            "uuid-child": {"Status": "Done"},
        }

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, db_props
            )

        assert "- Parent" in lines
        assert "  Type:: Project" in lines
        assert "  - Child" in lines
        assert "    Status:: Done" in lines


class TestFeatureFlagIntegration:
    """Tests that LOGSEQ_DB_MODE correctly gates DB-mode API calls."""

    @responses.activate
    def test_get_page_content_skips_db_queries_without_flag(self):
        """get_page_content does NOT call get_blocks_db_properties when flag is off."""
        api_url = "http://localhost:12315/api"
        # Call 1: getPage
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "Test", "originalName": "Test", "uuid": "page-uuid"},
            status=200)
        # Call 2: getPageBlocksTree
        responses.add(responses.POST, api_url,
            json=[{"id": 1, "uuid": "u1", "content": "Hello", "properties": {}, "children": []}],
            status=200)

        handler = GetPageContentToolHandler()

        with patch("mcp_logseq.tools._db_mode", False):
            result = handler.run_tool({"page_name": "Test"})

        # Only 2 API calls (getPage + getPageBlocksTree), no datascript queries
        assert len(responses.calls) == 2
        for call in responses.calls:
            body = json.loads(call.request.body)
            assert body["method"] != "logseq.DB.datascriptQuery"

    @responses.activate
    def test_set_block_properties_blocked_without_flag(self):
        """set_block_properties returns error when LOGSEQ_DB_MODE is off."""
        from mcp_logseq.tools import SetBlockPropertiesToolHandler

        handler = SetBlockPropertiesToolHandler()

        with patch("mcp_logseq.tools._db_mode", False):
            result = handler.run_tool({
                "block_uuid": "test-uuid",
                "properties": {"Status": "Active"},
            })

        assert "LOGSEQ_DB_MODE=true" in result[0].text
        assert len(responses.calls) == 0  # No API calls made
