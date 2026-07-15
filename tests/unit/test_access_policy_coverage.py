"""Structural guarantee for declarative access control (architecture review A4).

Enforcement is no longer hand-wired at the top of each handler's ``run_tool``;
handlers declare an ``access_policy`` list that the base ``ToolHandler.run_tool``
runs at a single choke point before dispatch. These tests pin that contract so a
future handler cannot silently ship without the right gate:

- every mutating/content handler declares the expected policy *types* on the
  right argument, and
- the base choke point actually enforces the declared policy before ``_run``.

If you add or rename a handler, update ``EXPECTED_POLICIES`` deliberately — that
edit is the audit trail for a security-boundary change.
"""

import pytest

from mcp_logseq import access
from mcp_logseq import tools


# Expected declarative policy per handler: {class: {(PolicyType, arg), ...}}.
# Order does not matter; the SET of (type, arg) pairs is the contract.
EXPECTED_POLICIES = {
    # Page handlers -----------------------------------------------------------
    tools.CreatePageToolHandler: {(access.NamespaceName, "title")},
    tools.GetPageContentToolHandler: {(access.NamespaceName, "page_name")},
    tools.DeletePageToolHandler: {
        (access.NamespaceName, "page_name"),
        (access.PageTag, "page_name"),
    },
    tools.UpdatePageToolHandler: {
        (access.NamespaceName, "page_name"),
        (access.PageTag, "page_name"),
    },
    tools.RenamePageToolHandler: {
        (access.NamespaceName, "old_name"),
        (access.NamespaceName, "new_name"),
        (access.PageTag, "old_name"),
    },
    tools.GetPageBacklinksToolHandler: {(access.NamespaceName, "page_name")},
    # Block handlers (identical namespace + tag pair on the uuid argument) -----
    tools.DeleteBlockToolHandler: {
        (access.BlockNamespace, "block_uuid"),
        (access.BlockTag, "block_uuid"),
    },
    tools.UpdateBlockToolHandler: {
        (access.BlockNamespace, "block_uuid"),
        (access.BlockTag, "block_uuid"),
    },
    tools.GetBlockToolHandler: {
        (access.BlockNamespace, "block_uuid"),
        (access.BlockTag, "block_uuid"),
    },
    tools.InsertNestedBlockToolHandler: {
        (access.BlockNamespace, "parent_block_uuid"),
        (access.BlockTag, "parent_block_uuid"),
    },
    tools.SetBlockPropertiesToolHandler: {
        (access.BlockNamespace, "block_uuid"),
        (access.BlockTag, "block_uuid"),
    },
    # Namespace-tree handlers (name-gated; results filtered in _run) -----------
    tools.GetPagesFromNamespaceToolHandler: {(access.NamespaceName, "namespace")},
    tools.GetPagesTreeFromNamespaceToolHandler: {(access.NamespaceName, "namespace")},
    # Result-filtering handlers: no pre-dispatch gate by design (they drop
    # restricted rows inside _run via is_page_blocked / bespoke filters).
    tools.ListPagesToolHandler: set(),
    tools.FindPagesByPropertyToolHandler: set(),
    tools.SearchToolHandler: set(),
    tools.QueryToolHandler: set(),
}


def _policy_pairs(handler_cls) -> set:
    return {(type(p), p.arg) for p in handler_cls.access_policy}


@pytest.mark.parametrize("handler_cls, expected", EXPECTED_POLICIES.items())
def test_handler_declares_expected_policy(handler_cls, expected):
    assert _policy_pairs(handler_cls) == expected


def test_every_core_handler_is_covered():
    """No core handler may escape the coverage table above.

    Every ``ToolHandler`` subclass re-exported from ``mcp_logseq.tools`` must
    appear in ``EXPECTED_POLICIES``. A new handler that isn't listed fails here,
    forcing a deliberate decision about its access policy.
    """
    exported = {
        getattr(tools, name)
        for name in tools.__all__
        if isinstance(getattr(tools, name), type)
        and issubclass(getattr(tools, name), tools.ToolHandler)
        and getattr(tools, name) is not tools.ToolHandler
    }
    missing = exported - set(EXPECTED_POLICIES)
    assert not missing, (
        f"Handlers missing from EXPECTED_POLICIES (declare their access "
        f"policy and add them to the table): {sorted(c.__name__ for c in missing)}"
    )


def test_base_choke_point_enforces_before_dispatch():
    """The declared policy must run before ``_run`` — proving the gate is not
    merely declared but actually executed by the base ``run_tool``."""

    calls = []

    class Boom(access.AccessPolicy):
        def enforce(self, api, args):
            calls.append("enforced")
            raise access.AccessDenied("blocked")

    class Probe(tools.ToolHandler):
        access_policy = [Boom()]

        def __init__(self):
            super().__init__("probe")

        def _run(self, api, args):
            calls.append("ran")
            return []

    from unittest.mock import patch, Mock

    with patch("mcp_logseq.tools._make_api", return_value=Mock()):
        with pytest.raises(access.AccessDenied):
            Probe().run_tool({})

    # Enforcement happened; _run never did.
    assert calls == ["enforced"]
