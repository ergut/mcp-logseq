"""Tests for mcp_logseq.access — lazy, cached ACL configuration.

Covers the A6/A7 refactor: the ACL lists live in a dedicated module shared by
``tools.py`` and ``vector/index.py``; loading is lazy (no import-time side
effects) and parses the config file only once for all three lists.
"""

import json
from unittest.mock import patch

import pytest

from mcp_logseq import access
from mcp_logseq.access import AccessConfig

_ENV_VARS = (
    "LOGSEQ_EXCLUDE_TAGS",
    "LOGSEQ_INCLUDE_NAMESPACES",
    "LOGSEQ_EXCLUDE_NAMESPACES",
    "LOGSEQ_CONFIG_FILE",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all ACL-related env vars and reset the access-config cache."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    access.get_access_config.cache_clear()
    yield monkeypatch
    access.get_access_config.cache_clear()


class TestLoadAccessConfig:
    def test_defaults_to_empty_lists(self, clean_env):
        acl = access.load_access_config()
        assert acl.exclude_tags == []
        assert acl.include_namespaces == []
        assert acl.exclude_namespaces == []
        assert acl.has_rules is False

    def test_reads_all_lists_from_env(self, clean_env):
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "private,secret")
        clean_env.setenv("LOGSEQ_INCLUDE_NAMESPACES", "work")
        clean_env.setenv("LOGSEQ_EXCLUDE_NAMESPACES", "work/secret")
        acl = access.load_access_config()
        assert acl.exclude_tags == ["private", "secret"]
        assert acl.include_namespaces == ["work"]
        assert acl.exclude_namespaces == ["work/secret"]
        assert acl.has_rules is True

    def test_reads_all_lists_from_config_file(self, clean_env, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {
                    "exclude_tags": ["private"],
                    "include_namespaces": ["work"],
                    "exclude_namespaces": ["work/secret"],
                }
            )
        )
        clean_env.setenv("LOGSEQ_CONFIG_FILE", str(path))
        acl = access.load_access_config()
        assert acl.exclude_tags == ["private"]
        assert acl.include_namespaces == ["work"]
        assert acl.exclude_namespaces == ["work/secret"]

    def test_env_var_overrides_config_file_per_list(self, clean_env, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {"exclude_tags": ["from-file"], "include_namespaces": ["file-ns"]}
            )
        )
        clean_env.setenv("LOGSEQ_CONFIG_FILE", str(path))
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "from-env")
        acl = access.load_access_config()
        assert acl.exclude_tags == ["from-env"]
        assert acl.include_namespaces == ["file-ns"]

    def test_parses_config_file_once_for_all_lists(self, clean_env, tmp_path):
        """A7: one load_access_config() call must read the file exactly once."""
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"exclude_tags": ["private"]}))
        clean_env.setenv("LOGSEQ_CONFIG_FILE", str(path))
        with patch(
            "mcp_logseq.access.read_config_file",
            wraps=access.read_config_file,
        ) as reader:
            access.load_access_config()
        assert reader.call_count == 1


class TestGetAccessConfig:
    def test_cached_across_calls(self, clean_env):
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "private")
        first = access.get_access_config()
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "changed")
        assert access.get_access_config() is first
        assert access.get_access_config().exclude_tags == ["private"]

    def test_cache_clear_reloads(self, clean_env):
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "private")
        assert access.get_access_config().exclude_tags == ["private"]
        clean_env.setenv("LOGSEQ_EXCLUDE_TAGS", "changed")
        access.get_access_config.cache_clear()
        assert access.get_access_config().exclude_tags == ["changed"]


class TestHasRules:
    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            ({}, False),
            ({"exclude_tags": ["private"]}, True),
            ({"include_namespaces": ["work"]}, True),
            ({"exclude_namespaces": ["work/secret"]}, True),
        ],
    )
    def test_has_rules(self, kwargs, expected):
        assert AccessConfig(**kwargs).has_rules is expected
