"""Tests for the write allow-list (LOGSEQ_WRITE_NAMESPACES)."""

import json
import logging
from unittest.mock import Mock, patch

import pytest

from mcp_logseq import access
from mcp_logseq.access import AccessConfig, AccessDenied
from mcp_logseq.tools import (
    CreatePageToolHandler,
    DeleteBlockToolHandler,
    DeletePageToolHandler,
    GetPageContentToolHandler,
    InsertNestedBlockToolHandler,
    RenamePageToolHandler,
    SetBlockPropertiesToolHandler,
    UpdateBlockToolHandler,
    UpdatePageToolHandler,
)

READ_ONLY = "is read-only for this assistant"


def _acl(include=None, exclude=None, write=None):
    return patch(
        "mcp_logseq.access.get_access_config",
        return_value=AccessConfig(
            include_namespaces=include or [],
            exclude_namespaces=exclude or [],
            write_namespaces=write or [],
        ),
    )


def _api(block_page=None):
    fake = Mock()
    fake.get_block_page_name.return_value = block_page
    fake.page_exists.return_value = False
    fake.get_page_content.return_value = None
    return fake, patch("mcp_logseq.tools._make_api", return_value=fake)


FAMILY = dict(include=["Family", "Beren"], write=["Beren"])


# --- page tools --------------------------------------------------------------


def test_create_page_allowed_inside_write_list(caplog):
    fake, api = _api()
    with _acl(**FAMILY), api, caplog.at_level(logging.INFO, "mcp-logseq"):
        CreatePageToolHandler().run_tool({"title": "Beren/Notes", "content": "secret"})
    fake.create_page_with_blocks.assert_called_once()
    assert "Write: tool=create_page page=Beren/Notes" in caplog.text
    assert "secret" not in caplog.text  # A5: never log content


@pytest.mark.parametrize(
    "handler, args",
    [
        (CreatePageToolHandler, {"title": "Family/Takvim"}),
        (UpdatePageToolHandler, {"page_name": "Family/Takvim", "content": "x"}),
        (DeletePageToolHandler, {"page_name": "Family/Takvim"}),
    ],
)
def test_page_write_denied_in_read_only_namespace(handler, args):
    fake, api = _api()
    with _acl(**FAMILY), api:
        with pytest.raises(AccessDenied, match=READ_ONLY):
            handler().run_tool(args)
    fake.create_page_with_blocks.assert_not_called()
    fake.update_page_with_blocks.assert_not_called()
    fake.delete_page.assert_not_called()


def test_read_still_allowed_in_read_only_namespace():
    fake, api = _api()
    with _acl(**FAMILY), api:
        GetPageContentToolHandler().run_tool({"page_name": "Family/Takvim"})
    fake.get_page_content.assert_called_once()


def test_read_denial_wins_for_hidden_page():
    """A page outside the read rules gets the read message, not the write one."""
    _, api = _api()
    with _acl(**FAMILY), api:
        with pytest.raises(AccessDenied, match="restricted") as exc:
            UpdatePageToolHandler().run_tool({"page_name": "Work/x", "content": "y"})
    assert READ_ONLY not in str(exc.value)


def test_write_list_never_widens_read_access():
    _, api = _api()
    with _acl(include=["Family"], write=["Beren"]), api:
        with pytest.raises(AccessDenied, match="restricted"):
            CreatePageToolHandler().run_tool({"title": "Beren/x"})


@pytest.mark.parametrize(
    "old, new",
    [("Beren/a", "Family/a"), ("Family/a", "Beren/a")],
)
def test_rename_across_write_boundary_denied(old, new):
    fake, api = _api()
    with _acl(**FAMILY), api:
        with pytest.raises(AccessDenied, match=READ_ONLY):
            RenamePageToolHandler().run_tool({"old_name": old, "new_name": new})
    fake.rename_page.assert_not_called()


def test_rename_inside_write_list_allowed_and_audited(caplog):
    fake, api = _api()
    with _acl(**FAMILY), api, caplog.at_level(logging.INFO, "mcp-logseq"):
        RenamePageToolHandler().run_tool({"old_name": "Beren/a", "new_name": "Beren/b"})
    fake.rename_page.assert_called_once_with("Beren/a", "Beren/b")
    assert "Write: tool=rename_page page=Beren/a -> Beren/b" in caplog.text


# --- block tools -------------------------------------------------------------


@pytest.mark.parametrize(
    "handler, args",
    [
        (UpdateBlockToolHandler, {"block_uuid": "u1", "content": "c"}),
        (DeleteBlockToolHandler, {"block_uuid": "u1"}),
        (InsertNestedBlockToolHandler, {"parent_block_uuid": "u1", "content": "c"}),
        (SetBlockPropertiesToolHandler, {"block_uuid": "u1", "properties": {"a": 1}}),
    ],
)
def test_block_write_denied_in_read_only_namespace(handler, args):
    _, api = _api(block_page="Family/Takvim")
    with _acl(**FAMILY), api:
        with pytest.raises(AccessDenied, match=READ_ONLY):
            handler().run_tool(args)


def test_block_write_allowed_inside_write_list(caplog):
    fake, api = _api(block_page="Beren/Notes")
    with _acl(**FAMILY), api, caplog.at_level(logging.INFO, "mcp-logseq"):
        DeleteBlockToolHandler().run_tool({"block_uuid": "u1"})
    fake.delete_block.assert_called_once_with("u1")
    assert "Write: tool=delete_block page=Beren/Notes" in caplog.text


def test_block_write_denied_when_owner_unresolved():
    """Fail-closed even without read namespace rules."""
    fake, api = _api(block_page=None)
    with _acl(write=["Beren"]), api:
        with pytest.raises(AccessDenied, match="cannot verify"):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u1"})
    fake.delete_block.assert_not_called()


# --- empty write list: unchanged behavior ------------------------------------


def test_empty_write_list_keeps_todays_behavior():
    fake, api = _api(block_page=None)
    with _acl(include=["Family"]), api:
        CreatePageToolHandler().run_tool({"title": "Family/Takvim"})
        DeletePageToolHandler().run_tool({"page_name": "Family/Takvim"})
    fake.create_page_with_blocks.assert_called_once()
    fake.delete_page.assert_called_once()

    fake, api = _api(block_page=None)
    with _acl(), api:
        DeleteBlockToolHandler().run_tool({"block_uuid": "u1"})
    fake.delete_block.assert_called_once_with("u1")
    fake.get_block_page_name.assert_not_called()  # no extra owner lookup


# --- loading -----------------------------------------------------------------


def test_write_namespaces_from_config_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"write_namespaces": ["Beren", "Inbox"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_WRITE_NAMESPACES", raising=False)
    assert access.load_access_config().write_namespaces == ["Beren", "Inbox"]


def test_write_namespaces_env_wins_over_config(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"write_namespaces": ["from-file"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_WRITE_NAMESPACES", "Beren, Inbox")
    assert access.load_access_config().write_namespaces == ["Beren", "Inbox"]


def test_write_namespaces_empty_by_default(monkeypatch):
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    monkeypatch.delenv("LOGSEQ_WRITE_NAMESPACES", raising=False)
    assert access.load_access_config().write_namespaces == []


def test_warns_when_write_namespace_outside_include(monkeypatch, caplog):
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    monkeypatch.setenv("LOGSEQ_INCLUDE_NAMESPACES", "Family")
    monkeypatch.setenv("LOGSEQ_WRITE_NAMESPACES", "Family/Beren,Beren")
    with caplog.at_level(logging.INFO, "mcp-logseq"):
        access.load_access_config()
    assert "Write namespaces: Family/Beren, Beren" in caplog.text
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "'Beren'" in warnings[0]
