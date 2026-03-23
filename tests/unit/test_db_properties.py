"""Tests for DB-mode property support (LOGSEQ_DB_MODE feature flag)."""

import json
import pytest
import responses
from unittest.mock import patch, Mock

from mcp_logseq.logseq import LogSeq
from mcp_logseq.tools import (
    GetPageContentToolHandler,
    _collect_block_uuids,
    _resolve_block_refs,
    _UUID_REF_PATTERN,
)


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
    """Tests for LogSeq.get_blocks_db_properties (batched)."""

    def test_processes_nested_blocks(self, logseq_client, db_blocks):
        """All blocks in tree (including children) are processed with batched queries."""
        queried_block_ids = []

        def mock_query(query):
            # Track which block IDs are queried for attributes
            for bid in [101, 102, 103]:
                if f'[{bid} ?a ?v]' in query:
                    queried_block_ids.append(bid)
                    if bid == 101:
                        return [[":user.property/status-abc", 201]]
                    return []
            # Batch ident resolution
            if ':db/ident' in query and 'or' in query.lower():
                return [[301, ":user.property/status-abc"]]
            if ':db/ident' in query:
                return [[301, ":user.property/status-abc"]]
            # Batch title resolution (entities 301=property name, 201=value)
            if 'or' in query.lower():
                return [[301, "title", "Status"], [201, "title", "Active"]]
            return []

        with patch.object(logseq_client, "datascript_query", side_effect=mock_query):
            result = logseq_client.get_blocks_db_properties(db_blocks)

        assert sorted(queried_block_ids) == [101, 102, 103]
        assert result == {"uuid-block-1": {"Status": "Active"}}

    def test_empty_blocks(self, logseq_client):
        """Empty block list returns empty dict."""
        result = logseq_client.get_blocks_db_properties([])
        assert result == {}

    def test_batched_reduces_query_count(self, logseq_client, db_blocks):
        """Batched approach uses significantly fewer queries than N+1."""
        query_count = 0

        def mock_query(query):
            nonlocal query_count
            query_count += 1
            for bid in [101, 102, 103]:
                if f'[{bid} ?a ?v]' in query:
                    if bid == 101:
                        return [[":user.property/p1", 201], [":user.property/p2", 202]]
                    return []
            if ':db/ident' in query:
                return [[301, ":user.property/p1"], [302, ":user.property/p2"]]
            # Batch title resolution
            return [[301, "title", "Prop1"], [302, "title", "Prop2"],
                    [201, "title", "Val1"], [202, "title", "Val2"]]

        with patch.object(logseq_client, "datascript_query", side_effect=mock_query):
            logseq_client.get_blocks_db_properties(db_blocks)

        # 3 blocks + 1 ident batch + 1 title batch = 5 queries
        # Without batching this would be 3 + (2*2 ident) + (2*2 + 2 prop) = 13+
        assert query_count == 5


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


class TestUuidRefResolution:
    """Tests for resolving [[uuid]] page references to [[Page Name]]."""

    def test_uuid_ref_pattern_matches(self):
        """Regex matches valid UUID references in double brackets."""
        content = "Link to [[69133208-abcd-4ef0-1234-567890abcdef]] here"
        matches = _UUID_REF_PATTERN.findall(content)
        assert matches == ["69133208-abcd-4ef0-1234-567890abcdef"]

    def test_uuid_ref_pattern_multiple(self):
        """Regex matches multiple UUID references."""
        content = "See [[aaaa1111-2222-3333-4444-555566667777]] and [[bbbb1111-2222-3333-4444-555566667777]]"
        matches = _UUID_REF_PATTERN.findall(content)
        assert len(matches) == 2

    def test_uuid_ref_pattern_ignores_non_uuids(self):
        """Regex does not match non-UUID bracket content."""
        content = "Link to [[My Page]] and [[Another Page]]"
        matches = _UUID_REF_PATTERN.findall(content)
        assert matches == []

    def test_uuid_ref_pattern_ignores_bare_uuids(self):
        """Regex does not match UUIDs outside of brackets."""
        content = "UUID is 69133208-abcd-4ef0-1234-567890abcdef"
        matches = _UUID_REF_PATTERN.findall(content)
        assert matches == []

    def test_collect_block_uuids_flat(self):
        """Collects UUIDs from flat block list."""
        blocks = [
            {"content": "See [[aaaa1111-2222-3333-4444-555566667777]]", "children": []},
            {"content": "And [[bbbb1111-2222-3333-4444-555566667777]]", "children": []},
        ]
        uuids = _collect_block_uuids(blocks)
        assert uuids == {"aaaa1111-2222-3333-4444-555566667777", "bbbb1111-2222-3333-4444-555566667777"}

    def test_collect_block_uuids_nested(self):
        """Collects UUIDs from nested children."""
        blocks = [
            {
                "content": "Parent [[aaaa1111-2222-3333-4444-555566667777]]",
                "children": [
                    {"content": "Child [[bbbb1111-2222-3333-4444-555566667777]]", "children": []},
                ],
            },
        ]
        uuids = _collect_block_uuids(blocks)
        assert len(uuids) == 2

    def test_collect_block_uuids_deduplicates(self):
        """Same UUID appearing twice is collected once."""
        blocks = [
            {"content": "A [[aaaa1111-2222-3333-4444-555566667777]]", "children": []},
            {"content": "B [[aaaa1111-2222-3333-4444-555566667777]]", "children": []},
        ]
        uuids = _collect_block_uuids(blocks)
        assert len(uuids) == 1

    def test_resolve_block_refs_replaces(self):
        """Resolved UUIDs are replaced with page names."""
        content = "See [[aaaa1111-2222-3333-4444-555566667777]] for details"
        uuid_map = {"aaaa1111-2222-3333-4444-555566667777": "Administratie"}
        result = _resolve_block_refs(content, uuid_map)
        assert result == "See [[Administratie]] for details"

    def test_resolve_block_refs_keeps_unresolved(self):
        """Unresolved UUIDs are left as-is."""
        content = "See [[aaaa1111-2222-3333-4444-555566667777]]"
        uuid_map = {}
        result = _resolve_block_refs(content, uuid_map)
        assert result == content

    def test_resolve_block_refs_mixed(self):
        """Mix of resolved and unresolved refs."""
        content = "A [[aaaa1111-2222-3333-4444-555566667777]] B [[bbbb1111-2222-3333-4444-555566667777]]"
        uuid_map = {"aaaa1111-2222-3333-4444-555566667777": "Page A"}
        result = _resolve_block_refs(content, uuid_map)
        assert "[[Page A]]" in result
        assert "[[bbbb1111-2222-3333-4444-555566667777]]" in result

    def test_format_block_tree_resolves_refs(self):
        """_format_block_tree replaces UUID refs when uuid_map is provided."""
        block = {
            "content": "Link to [[aaaa1111-2222-3333-4444-555566667777]]",
            "uuid": "block-1",
            "properties": {},
            "children": [],
        }
        uuid_map = {"aaaa1111-2222-3333-4444-555566667777": "My Page"}

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, None, uuid_map
            )

        assert "[[My Page]]" in lines[0]
        assert "aaaa1111" not in lines[0]

    def test_format_block_tree_no_uuid_map(self):
        """_format_block_tree leaves UUID refs when no map is provided."""
        block = {
            "content": "Link to [[aaaa1111-2222-3333-4444-555566667777]]",
            "uuid": "block-1",
            "properties": {},
            "children": [],
        }

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, None, None
            )

        assert "aaaa1111-2222-3333-4444-555566667777" in lines[0]

    def test_format_block_tree_resolves_in_children(self):
        """UUID refs in child blocks are also resolved."""
        block = {
            "content": "Parent",
            "uuid": "parent-1",
            "properties": {},
            "children": [
                {
                    "content": "Child links to [[aaaa1111-2222-3333-4444-555566667777]]",
                    "uuid": "child-1",
                    "properties": {},
                    "children": [],
                }
            ],
        }
        uuid_map = {"aaaa1111-2222-3333-4444-555566667777": "Resolved Page"}

        with patch("mcp_logseq.tools._db_mode", True):
            lines = GetPageContentToolHandler._format_block_tree(
                block, 0, -1, None, uuid_map
            )

        child_line = [l for l in lines if "Child" in l][0]
        assert "[[Resolved Page]]" in child_line


class TestResolvePageUuids:
    """Tests for the LogSeq.resolve_page_uuids API method."""

    @responses.activate
    def test_resolve_success(self):
        """Successfully resolves page UUIDs to names."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "administratie", "originalName": "Administratie", "uuid": "uuid-1"},
            status=200)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["uuid-1"])

        assert result == {"uuid-1": "Administratie"}
        body = json.loads(responses.calls[0].request.body)
        assert body["method"] == "logseq.Editor.getPage"
        assert body["args"] == ["uuid-1"]

    @responses.activate
    def test_resolve_prefers_originalName(self):
        """Uses originalName over name when available."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "my page", "originalName": "My Page", "uuid": "uuid-1"},
            status=200)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["uuid-1"])

        assert result["uuid-1"] == "My Page"

    @responses.activate
    def test_resolve_not_found(self):
        """UUIDs that don't resolve to a page are omitted."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url, body="null",
            content_type="application/json", status=200)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["bad-uuid"])

        assert result == {}

    @responses.activate
    def test_resolve_deduplicates(self):
        """Duplicate UUIDs result in a single API call."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "page", "originalName": "Page", "uuid": "uuid-1"},
            status=200)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["uuid-1", "uuid-1", "uuid-1"])

        assert len(responses.calls) == 1
        assert result == {"uuid-1": "Page"}

    @responses.activate
    def test_resolve_api_error_skips(self):
        """API errors for individual UUIDs are silently skipped."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url, json={"error": "fail"}, status=500)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["uuid-1"])

        assert result == {}

    @responses.activate
    def test_resolve_multiple_uuids(self):
        """Resolves multiple distinct UUIDs."""
        api_url = "http://127.0.0.1:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "page a", "originalName": "Page A", "uuid": "uuid-a"},
            status=200)
        responses.add(responses.POST, api_url,
            json={"id": 2, "name": "page b", "originalName": "Page B", "uuid": "uuid-b"},
            status=200)

        client = LogSeq(api_key="test", host="127.0.0.1", port=12315)
        result = client.resolve_page_uuids(["uuid-a", "uuid-b"])

        assert len(result) == 2
        assert "Page A" in result.values()
        assert "Page B" in result.values()


class TestGetPageContentResolveRefs:
    """Tests for resolve_refs integration in get_page_content tool."""

    @responses.activate
    def test_resolve_refs_enabled_in_db_mode(self):
        """UUID refs are resolved when LOGSEQ_DB_MODE is on and resolve_refs is true."""
        api_url = "http://localhost:12315/api"
        # getPage
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "Test", "originalName": "Test", "uuid": "page-uuid"},
            status=200)
        # getPageBlocksTree
        responses.add(responses.POST, api_url,
            json=[{
                "id": 1, "uuid": "b1",
                "content": "See [[aaaa1111-2222-3333-4444-555566667777]]",
                "properties": {}, "children": [],
            }],
            status=200)
        # resolve_page_uuids -> getPage for the UUID
        responses.add(responses.POST, api_url,
            json={"id": 2, "name": "target", "originalName": "Target Page", "uuid": "aaaa1111-2222-3333-4444-555566667777"},
            status=200)

        handler = GetPageContentToolHandler()
        with patch("mcp_logseq.tools._db_mode", True):
            result = handler.run_tool({"page_name": "Test"})

        assert "[[Target Page]]" in result[0].text
        assert "aaaa1111" not in result[0].text

    @patch.dict("os.environ", {"LOGSEQ_API_TOKEN": "test_token"})
    @patch("mcp_logseq.tools.logseq.LogSeq")
    def test_resolve_refs_disabled(self, mock_logseq_class):
        """UUID refs are NOT resolved when resolve_refs=false."""
        mock_api = Mock()
        mock_api.get_page_content.return_value = {
            "page": {"name": "Test", "originalName": "Test", "uuid": "page-uuid"},
            "blocks": [{
                "id": 1, "uuid": "b1",
                "content": "See [[aaaa1111-2222-3333-4444-555566667777]]",
                "properties": {}, "children": [],
            }],
        }
        mock_api.get_blocks_db_properties.return_value = {}
        mock_logseq_class.return_value = mock_api

        handler = GetPageContentToolHandler()
        with patch("mcp_logseq.tools._db_mode", True):
            result = handler.run_tool({"page_name": "Test", "resolve_refs": False})

        assert "aaaa1111-2222-3333-4444-555566667777" in result[0].text
        # resolve_page_uuids should NOT be called
        mock_api.resolve_page_uuids.assert_not_called()

    @responses.activate
    def test_resolve_refs_skipped_in_markdown_mode(self):
        """No UUID resolution in markdown mode."""
        api_url = "http://localhost:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "Test", "originalName": "Test", "uuid": "page-uuid"},
            status=200)
        responses.add(responses.POST, api_url,
            json=[{
                "id": 1, "uuid": "b1",
                "content": "See [[My Page]]",
                "properties": {}, "children": [],
            }],
            status=200)

        handler = GetPageContentToolHandler()
        with patch("mcp_logseq.tools._db_mode", False):
            result = handler.run_tool({"page_name": "Test"})

        assert "[[My Page]]" in result[0].text
        assert len(responses.calls) == 2

    @responses.activate
    def test_json_format_includes_resolved_refs(self):
        """JSON format includes resolved_refs mapping in DB mode."""
        api_url = "http://localhost:12315/api"
        responses.add(responses.POST, api_url,
            json={"id": 1, "name": "Test", "originalName": "Test", "uuid": "page-uuid"},
            status=200)
        responses.add(responses.POST, api_url,
            json=[{
                "id": 1, "uuid": "b1",
                "content": "See [[aaaa1111-2222-3333-4444-555566667777]]",
                "properties": {}, "children": [],
            }],
            status=200)
        responses.add(responses.POST, api_url,
            json={"id": 2, "name": "target", "originalName": "Target", "uuid": "aaaa1111-2222-3333-4444-555566667777"},
            status=200)

        handler = GetPageContentToolHandler()
        with patch("mcp_logseq.tools._db_mode", True):
            result = handler.run_tool({"page_name": "Test", "format": "json"})

        parsed = json.loads(result[0].text)
        assert "resolved_refs" in parsed
        assert parsed["resolved_refs"]["aaaa1111-2222-3333-4444-555566667777"] == "Target"
