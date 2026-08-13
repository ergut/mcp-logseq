"""
Tests that block uuids survive a page rewrite.

A block carrying an explicit ``id:: <uuid>`` is the target of ``((uuid))``
references elsewhere in the graph. If a rewrite mints new uuids, those
references dangle and Logseq rewrites them as plain text in the referring
files — content loss well outside the page being written.
"""

import json

import responses

from mcp_logseq.parser import parse_content

URL = "http://127.0.0.1:12315/api"

BLOCK_UUID = "6a7d0147-dc0e-4ae1-b701-be4289116f48"


def _calls_for(method):
    return [c for c in responses.calls if method in str(c.request.body)]


def _body(call):
    return json.loads(call.request.body)


def _add_replace_mocks(*, first_block_props=None):
    """Register the HTTP mocks for a replace-mode update on a one-block page."""
    responses.add(responses.POST, URL, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
    responses.add(responses.POST, URL, json=[{"uuid": "old-1", "content": "Old"}], status=200)  # clear: get blocks
    responses.add(responses.POST, URL, json=True, status=200)  # removeBlock
    responses.add(responses.POST, URL, json={"uuid": "anchor-1", "content": ""}, status=200)  # appendBlockInPage anchor
    responses.add(responses.POST, URL, json=[{"uuid": "new-1"}], status=200)  # insertBatchBlock
    responses.add(responses.POST, URL, json=[{"uuid": "anchor-1", "content": "", "properties": first_block_props or {}}], status=200)  # _resolve_first_block
    responses.add(responses.POST, URL, json=True, status=200)  # removeBlock / upsertBlockProperty (repeats)


class TestKeepUUID:
    """insertBatchBlock must be told to honour the id:: it was handed."""

    @responses.activate
    def test_batch_insert_requests_keep_uuid(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page", [{"content": f"## Meeting\nid:: {BLOCK_UUID}"}], mode="replace"
        )

        batch_calls = _calls_for("insertBatchBlock")
        assert len(batch_calls) == 1
        assert _body(batch_calls[0])["args"][2]["keepUUID"] is True

    @responses.activate
    def test_append_mode_also_keeps_uuids(self, logseq_client):
        responses.add(responses.POST, URL, json=[{"name": "Test Page", "originalName": "Test Page"}], status=200)  # list_pages
        responses.add(responses.POST, URL, json=[{"uuid": "block-1", "content": "Existing"}], status=200)  # get last block
        responses.add(responses.POST, URL, json=[{"uuid": "block-2"}], status=200)  # insertBatchBlock

        logseq_client.update_page_with_blocks(
            "Test Page", [{"content": f"Appended\nid:: {BLOCK_UUID}"}], mode="append"
        )

        assert _body(_calls_for("insertBatchBlock")[0])["args"][2]["keepUUID"] is True


class TestMalformedIdsFallBack:
    """A uuid Logseq won't parse must not take the page's content down with it.

    With keepUUID set, Logseq discards the entire batch when any id is malformed
    — and still answers as if the write succeeded, so the page silently ends up
    empty. Generated uuids are the lesser loss.
    """

    @responses.activate
    def test_malformed_id_drops_keep_uuid(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page",
            # Well-formed length and grouping, but not an RFC 4122 variant
            [{"content": "## Meeting\nid:: 11111111-2222-3333-4444-555555555555"}],
            mode="replace",
        )

        assert _body(_calls_for("insertBatchBlock")[0])["args"][2]["keepUUID"] is False

    @responses.activate
    def test_one_bad_id_disables_keep_uuid_for_the_whole_batch(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page",
            [
                {"content": f"## Good\nid:: {BLOCK_UUID}"},
                {"content": "## Bad", "children": [{"content": "id:: not-a-uuid"}]},
            ],
            mode="replace",
        )

        assert _body(_calls_for("insertBatchBlock")[0])["args"][2]["keepUUID"] is False

    @responses.activate
    def test_id_passed_as_a_property_is_validated_too(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page",
            [{"content": "## Meeting", "properties": {"id": "nope"}}],
            mode="replace",
        )

        assert _body(_calls_for("insertBatchBlock")[0])["args"][2]["keepUUID"] is False

    @responses.activate
    def test_blocks_without_ids_still_keep_uuid(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page", [{"content": "plain block"}], mode="replace"
        )

        assert _body(_calls_for("insertBatchBlock")[0])["args"][2]["keepUUID"] is True


class TestReplaceRoutesEveryBlockThroughBatch:
    """The first block must not take a different write path from the rest.

    appendBlockInPage cannot carry a uuid, so a first block written through it
    loses its id:: even when the remaining blocks keep theirs.
    """

    @responses.activate
    def test_first_block_goes_through_batch_insert(self, logseq_client):
        _add_replace_mocks()

        blocks = [
            {"content": f"## First\nid:: {BLOCK_UUID}", "children": [{"content": "child"}]},
            {"content": "## Second"},
        ]
        logseq_client.update_page_with_blocks("Test Page", blocks, mode="replace")

        # The anchor is empty — no real content is written through appendBlockInPage
        append_calls = _calls_for("appendBlockInPage")
        assert len(append_calls) == 1
        assert _body(append_calls[0])["args"][1] == ""

        batch_calls = _calls_for("insertBatchBlock")
        assert len(batch_calls) == 1
        payload = _body(batch_calls[0])["args"][1]
        assert [b["content"] for b in payload] == [
            f"## First\nid:: {BLOCK_UUID}",
            "## Second",
        ]
        assert payload[0]["children"] == [{"content": "child"}]

    @responses.activate
    def test_anchor_is_deleted_when_page_has_no_properties(self, logseq_client):
        _add_replace_mocks()

        logseq_client.update_page_with_blocks(
            "Test Page", [{"content": "Content"}], mode="replace"
        )

        removed = [_body(c)["args"][0] for c in _calls_for("removeBlock")]
        assert "anchor-1" in removed


class TestPagePropertiesStayOffContentBlocks:
    """Page properties belong in their own first block on file graphs.

    Logseq stores them as ``key:: value`` lines in the page's first block. If
    the rewrite deletes the empty anchor, the first block of real content
    becomes the property carrier and the properties are silently glued onto it.
    """

    @responses.activate
    def test_file_graph_keeps_anchor_as_property_block(self, logseq_client):
        _add_replace_mocks(first_block_props={"tags": "#Old"})

        logseq_client.update_page_with_blocks(
            "Test Page",
            [{"content": "Dev meeting series for [[Company/ProfitPath]]"}],
            properties={"tags": "#Company/ProfitPath"},
            mode="replace",
        )

        # The anchor survives the rewrite ...
        removed = [_body(c)["args"][0] for c in _calls_for("removeBlock")]
        assert "anchor-1" not in removed

        # ... and carries the page properties instead of the content block
        upserts = _calls_for("upsertBlockProperty")
        assert len(upserts) == 1
        assert _body(upserts[0])["args"][0] == "anchor-1"
        assert _body(upserts[0])["args"][1] == "tags"

    @responses.activate
    def test_db_graph_drops_the_anchor(self, logseq_client_db):
        """DB graphs keep properties on the page entity, so no anchor is needed."""
        _add_replace_mocks()

        logseq_client_db.update_page_with_blocks(
            "Test Page",
            [{"content": "Content"}],
            properties={"tags": "#Company/ProfitPath"},
            mode="replace",
        )

        removed = [_body(c)["args"][0] for c in _calls_for("removeBlock")]
        assert "anchor-1" in removed
        assert len(_calls_for("setPageProperties")) == 1


class TestParserToBatchRoundTrip:
    """The id:: has to survive parsing to reach insertBatchBlock at all."""

    def test_id_property_is_carried_into_batch_content(self):
        markdown = (
            f"- ## [[Aug 13th, 2026]] — Getting up and running locally\n"
            f"  id:: {BLOCK_UUID}\n"
            f"\t- local setup\n"
        )

        batch = parse_content(markdown).to_batch_format()

        assert len(batch) == 1
        assert batch[0]["content"] == (
            f"## [[Aug 13th, 2026]] — Getting up and running locally\nid:: {BLOCK_UUID}"
        )
        assert batch[0]["children"] == [{"content": "local setup"}]
