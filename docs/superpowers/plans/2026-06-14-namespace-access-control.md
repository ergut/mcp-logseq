# Namespace Bazlı Erişim Kontrolü — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mcp-logseq sunucusuna, mevcut tag bazlı `exclude_tags` mekanizmasıyla yan yana çalışan, namespace bazlı include/exclude erişim kontrolü eklemek; tüm okuma, yazma/silme ve vektör arama araçlarında uygulamak.

**Architecture:** Config katmanına `exclude_tags` ile simetrik iki yükleyici (`load_include_namespaces`, `load_exclude_namespaces`) eklenir; ortak bir `_load_csv_config` helper'ı çıkarılır. `tools.py` içine saf eşleştirme fonksiyonları (`_namespace_matches`, `_is_namespace_blocked`) ve enforcement helper'ları (`_enforce_namespace_access`, `_enforce_block_namespace_access`, `AccessDenied`) eklenir. Sayfa adı taşıyan araçlar pre-flight kontrol yapar; block-UUID araçları block→sayfa adını API'den çözüp kontrol eder; liste/arama/vektör araçları sonuç setini sessizce filtreler.

**Tech Stack:** Python 3, `uv`, `pytest`, `unittest.mock`. Logseq HTTP JSON-RPC API.

---

## Tasarım kuralları (spec'ten)

- **Eşleştirme:** segment bazlı, case-insensitive. `work` → `work` ve `work/...` eşleşir; `workshop` eşleşmez.
- **Öncelik:** exclude kazanır. Sonra: include doluysa ve hiçbirine uymuyorsa engelle (katı allow-list; namespace'siz sayfalar da gizlenir).
- **Katmanlar:** tag (mevcut) VEYA namespace (yeni) → engelle.
- **Görünürlük:** liste/arama/vektör sessiz filtre; doğrudan erişim/yazma/silme `AccessDenied` ile sert hata.
- **Block araçları (fail-closed):** namespace kuralı tanımlıyken block'un sayfası çözülemezse erişim reddedilir. Hiç namespace kuralı yoksa özellik kapalıdır, hiçbir şey değişmez.
- **Sınır:** Yazma araçlarında yalnızca **namespace** (isim bazlı) zorlanır; tag bazlı kontrol mevcut okuma noktalarında olduğu gibi kalır (tag için sayfa property'leri gerekir; bu özelliğin kapsamı namespace'tir).

---

## Dosya yapısı

- **Modify** `src/mcp_logseq/config.py` — `_load_csv_config` helper, `load_include_namespaces`, `load_exclude_namespaces`; `load_exclude_tags` refactor; docstring güncelle.
- **Modify** `src/mcp_logseq/logseq.py` — `get_block_page_name`, `_get_page_name_by_id` API helper'ları.
- **Modify** `src/mcp_logseq/tools.py` — eşleştirme + enforcement helper'ları; modül seviyesi config; tüm ilgili handler'lara enforcement/filtreleme.
- **Modify** `src/mcp_logseq/vector/index.py` — vektör arama sonuç filtresi.
- **Create** `tests/unit/test_namespace_access.py` — tüm yeni birim ve handler testleri.
- **Modify** `tests/unit/test_logseq_api.py` — `get_block_page_name` testleri (mevcut API test dosyasıyla aynı yerde).

---

## Task 1: Config yükleyicileri ve ortak helper

**Files:**
- Modify: `src/mcp_logseq/config.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` dosyasını oluştur:

```python
"""Tests for namespace-based access control."""

import json
import pytest
from unittest.mock import patch, Mock

from mcp_logseq.config import (
    load_include_namespaces,
    load_exclude_namespaces,
    load_exclude_tags,
)


# --- load_include_namespaces / load_exclude_namespaces ---

def test_include_empty_when_nothing_set(monkeypatch):
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_include_namespaces() == []


def test_include_reads_from_env(monkeypatch):
    monkeypatch.setenv("LOGSEQ_INCLUDE_NAMESPACES", "work, projects")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_include_namespaces() == ["work", "projects"]


def test_exclude_reads_from_env(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_NAMESPACES", "finance,personal")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_namespaces() == ["finance", "personal"]


def test_include_env_takes_priority_over_config(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"include_namespaces": ["from-file"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOGSEQ_INCLUDE_NAMESPACES", "from-env")
    assert load_include_namespaces() == ["from-env"]


def test_include_reads_from_config_list(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"include_namespaces": ["work", "projects"]}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == ["work", "projects"]


def test_exclude_reads_from_config_comma_string(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"exclude_namespaces": "finance, personal"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_EXCLUDE_NAMESPACES", raising=False)
    assert load_exclude_namespaces() == ["finance", "personal"]


def test_namespace_empty_when_config_missing_key(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"logseq_graph_path": "/x"}))
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    monkeypatch.delenv("LOGSEQ_EXCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == []
    assert load_exclude_namespaces() == []


def test_namespace_empty_when_config_malformed(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("not json{{{")
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", str(path))
    monkeypatch.delenv("LOGSEQ_INCLUDE_NAMESPACES", raising=False)
    assert load_include_namespaces() == []


def test_exclude_tags_still_works_after_refactor(monkeypatch):
    monkeypatch.setenv("LOGSEQ_EXCLUDE_TAGS", "private, secret")
    monkeypatch.delenv("LOGSEQ_CONFIG_FILE", raising=False)
    assert load_exclude_tags() == ["private", "secret"]
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_include_namespaces'`

- [ ] **Step 3: `_load_csv_config` helper'ını ekle ve `load_exclude_tags`'i ona bağla**

`src/mcp_logseq/config.py` içinde, mevcut `load_exclude_tags` fonksiyonunu (satır ~113-148) aşağıdakiyle değiştir:

```python
def _load_csv_config(env_var: str, config_key: str) -> list[str]:
    """Load a comma/list config value from an env var or the config file root.

    Priority: env var > config file root key > [] (no value).
    env var: comma-separated string. config file: list or comma-separated string.
    Strips whitespace and drops empties. Never raises.
    """
    env_val = os.getenv(env_var, "").strip()
    if env_val:
        items = [t.strip() for t in env_val.split(",") if t.strip()]
        if items:
            logger.info(f"Loaded {len(items)} entries from {env_var}")
            return items

    config_path = os.getenv("LOGSEQ_CONFIG_FILE")
    if not config_path:
        return []
    config_path = os.path.expanduser(config_path)
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path) as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to parse config file for {config_key} {config_path}: {e}")
        return []

    raw_val = raw.get(config_key, [])
    if isinstance(raw_val, list):
        items = [str(t).strip() for t in raw_val if str(t).strip()]
    elif isinstance(raw_val, str):
        items = [t.strip() for t in raw_val.split(",") if t.strip()]
    else:
        items = []
    if items:
        logger.info(f"Loaded {len(items)} entries for '{config_key}' from config file root")
    return items


def load_exclude_tags() -> list[str]:
    """Load top-level exclude_tags. Priority: env var > config file > []."""
    return _load_csv_config("LOGSEQ_EXCLUDE_TAGS", "exclude_tags")


def load_include_namespaces() -> list[str]:
    """Load allow-list namespaces. Priority: env var > config file > []."""
    return _load_csv_config("LOGSEQ_INCLUDE_NAMESPACES", "include_namespaces")


def load_exclude_namespaces() -> list[str]:
    """Load deny-list namespaces. Priority: env var > config file > []."""
    return _load_csv_config("LOGSEQ_EXCLUDE_NAMESPACES", "exclude_namespaces")
```

Ayrıca dosya başındaki örnek config docstring'ine (satır ~7-24) `include_namespaces`/`exclude_namespaces` ekle:

```python
  "exclude_tags": ["private", "secret"],
  "include_namespaces": ["work", "projects"],
  "exclude_namespaces": ["work/secret"],
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py tests/unit/test_exclude_tags.py -v`
Expected: PASS (yeni testler + mevcut exclude_tags regresyonu)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/config.py tests/unit/test_namespace_access.py
git commit -m "feat: add namespace config loaders with shared csv helper"
```

---

## Task 2: Eşleştirme ve enforcement helper'ları (`tools.py`)

**Files:**
- Modify: `src/mcp_logseq/tools.py` (helper'lar `_is_page_excluded` tanımından hemen sonra, satır ~118)
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
# --- _namespace_matches / _is_namespace_blocked / _is_page_blocked ---

from mcp_logseq.tools import (
    _namespace_matches,
    _is_namespace_blocked,
    _is_page_blocked,
    AccessDenied,
)


def test_namespace_matches_exact():
    assert _namespace_matches("work", "work") is True


def test_namespace_matches_child():
    assert _namespace_matches("work/projects/q3", "work") is True


def test_namespace_matches_rejects_prefix_lookalike():
    assert _namespace_matches("workshop", "work") is False


def test_namespace_matches_case_insensitive():
    assert _namespace_matches("Work/Projects", "work") is True


def test_namespace_matches_trailing_slash_in_rule():
    assert _namespace_matches("work/x", "work/") is True


def test_blocked_when_excluded():
    assert _is_namespace_blocked("finance/q3", [], ["finance"]) is True


def test_exclude_wins_over_include():
    assert _is_namespace_blocked("work/secret/x", ["work"], ["work/secret"]) is True


def test_allowed_when_in_include():
    assert _is_namespace_blocked("work/projects", ["work"], []) is False


def test_strict_allowlist_blocks_non_matching():
    assert _is_namespace_blocked("personal/diary", ["work"], []) is True


def test_strict_allowlist_blocks_top_level_unnamespaced_page():
    assert _is_namespace_blocked("Fikirler", ["work"], []) is True


def test_no_rules_never_blocks():
    assert _is_namespace_blocked("anything/here", [], []) is False


def test_is_page_blocked_by_tag(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", ["private"]), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", []):
        page = {"properties": {"tags": ["private"]}}
        assert _is_page_blocked(page, "work/x") is True


def test_is_page_blocked_by_namespace(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", []), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", ["finance"]):
        page = {"properties": {"tags": []}}
        assert _is_page_blocked(page, "finance/q3") is True


def test_is_page_blocked_false_when_clear(monkeypatch):
    with patch("mcp_logseq.tools._exclude_tags", ["private"]), \
         patch("mcp_logseq.tools._include_namespaces", []), \
         patch("mcp_logseq.tools._exclude_namespaces", ["finance"]):
        page = {"properties": {"tags": ["notes"]}}
        assert _is_page_blocked(page, "work/x") is False
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k "namespace or page_blocked or allowlist or exclude_wins" -v`
Expected: FAIL — `ImportError: cannot import name '_namespace_matches'`

- [ ] **Step 3: Helper'ları implement et**

`src/mcp_logseq/tools.py` başındaki import (satır ~10) güncelle:

```python
from .config import load_exclude_tags, load_include_namespaces, load_exclude_namespaces
```

Modül seviyesi config (satır ~59, `_exclude_tags = load_exclude_tags()` yanına):

```python
_exclude_tags: list[str] = load_exclude_tags()
_include_namespaces: list[str] = load_include_namespaces()
_exclude_namespaces: list[str] = load_exclude_namespaces()
```

`_is_page_excluded` tanımından hemen sonra (satır ~118) ekle:

```python
class AccessDenied(RuntimeError):
    """Raised when a tool is blocked from accessing a restricted page."""


def _namespace_matches(page_name: str, ns: str) -> bool:
    """Segment-based, case-insensitive namespace match.

    'work' matches 'work' and 'work/...'; it does NOT match 'workshop'.
    """
    p = page_name.lower()
    n = ns.lower().rstrip("/")
    if not n:
        return False
    return p == n or p.startswith(n + "/")


def _is_namespace_blocked(page_name: str, include: list[str], exclude: list[str]) -> bool:
    """Apply namespace rules. Exclude wins; include is a strict allow-list."""
    if any(_namespace_matches(page_name, n) for n in exclude):
        return True
    if include and not any(_namespace_matches(page_name, n) for n in include):
        return True
    return False


def _is_page_blocked(page: dict | None, page_name: str) -> bool:
    """Combined tag OR namespace block check (used for result filtering)."""
    if page and _is_page_excluded(page, _exclude_tags):
        return True
    return _is_namespace_blocked(page_name, _include_namespaces, _exclude_namespaces)


def _enforce_namespace_access(page_name: str) -> None:
    """Raise AccessDenied if page_name is blocked by namespace rules.

    Name-based only (no tag check — that needs fetched page properties).
    """
    if _is_namespace_blocked(page_name, _include_namespaces, _exclude_namespaces):
        raise AccessDenied(
            f"Access denied: page '{page_name}' is restricted "
            f"and cannot be accessed by this assistant."
        )


def _enforce_block_namespace_access(api, block_uuid: str) -> None:
    """Resolve a block's owning page and enforce namespace rules.

    Fail-closed: when namespace rules are configured but the page cannot be
    resolved, access is denied. When no namespace rules exist, this is a no-op.
    """
    if not _include_namespaces and not _exclude_namespaces:
        return
    page_name = api.get_block_page_name(block_uuid)
    if page_name is None:
        raise AccessDenied(
            f"Access denied: cannot verify the namespace of block '{block_uuid}'."
        )
    _enforce_namespace_access(page_name)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/tools.py tests/unit/test_namespace_access.py
git commit -m "feat: add namespace matching and enforcement helpers"
```

---

## Task 3: Block→sayfa adı çözümü (`logseq.py`)

**Files:**
- Modify: `src/mcp_logseq/logseq.py` (`get_block` tanımından sonra, satır ~1092)
- Test: `tests/unit/test_logseq_api.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_logseq_api.py` sonuna ekle (dosya başındaki mevcut `from mcp_logseq.logseq import LogSeq` ve `unittest.mock` importlarını kullanır — yoksa ekle):

```python
from unittest.mock import patch, Mock
from mcp_logseq.logseq import LogSeq


def _api():
    return LogSeq(api_key="t", api_base_url="http://localhost:12315")


def test_get_block_page_name_from_inline_name():
    api = _api()
    with patch.object(api, "get_block", return_value={"page": {"originalName": "work/projects"}}):
        assert api.get_block_page_name("uuid-1") == "work/projects"


def test_get_block_page_name_resolves_by_id():
    api = _api()
    with patch.object(api, "get_block", return_value={"page": {"id": 42}}), \
         patch.object(api, "_get_page_name_by_id", return_value="finance/q3") as m:
        assert api.get_block_page_name("uuid-2") == "finance/q3"
        m.assert_called_once_with(42)


def test_get_block_page_name_none_when_no_page():
    api = _api()
    with patch.object(api, "get_block", return_value={"content": "x"}):
        assert api.get_block_page_name("uuid-3") is None


def test_get_block_page_name_none_when_block_missing():
    api = _api()
    with patch.object(api, "get_block", side_effect=ValueError("not found")):
        assert api.get_block_page_name("uuid-4") is None
```

Not: `LogSeq.__init__` imzasını doğrula. Eğer parametre adı farklıysa (`api_base_url` yerine başka), `_api()` çağrısını gerçek imzaya göre düzelt — `grep -n "def __init__" src/mcp_logseq/logseq.py`.

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_logseq_api.py -k get_block_page_name -v`
Expected: FAIL — `AttributeError: 'LogSeq' object has no attribute 'get_block_page_name'`

- [ ] **Step 3: API helper'larını implement et**

`src/mcp_logseq/logseq.py` içinde, `get_block` metodunun bittiği yere (satır ~1092, `resolve_page_uuids`'ten önce) ekle:

```python
    def _get_page_name_by_id(self, page_id) -> str | None:
        """Resolve a page's human-readable name from its db id (or uuid)."""
        url = self.get_base_url()
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.getPage", "args": [page_id]},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            page = response.json()
            if page and isinstance(page, dict):
                return page.get("originalName") or page.get("name")
        except Exception as e:
            logger.warning(f"Could not resolve page name for id '{page_id}': {e}")
        return None

    def get_block_page_name(self, block_uuid: str) -> str | None:
        """Resolve the name of the page that owns a given block.

        Returns None if the page cannot be determined.
        """
        try:
            block = self.get_block(block_uuid, include_children=False)
        except Exception as e:
            logger.warning(f"Could not fetch block '{block_uuid}' for page resolution: {e}")
            return None
        if not block or not isinstance(block, dict):
            return None
        page_ref = block.get("page")
        if isinstance(page_ref, dict):
            name = page_ref.get("originalName") or page_ref.get("name")
            if name:
                return name
            page_id = page_ref.get("id")
            if page_id is not None:
                return self._get_page_name_by_id(page_id)
        return None
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_logseq_api.py -k get_block_page_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/logseq.py tests/unit/test_logseq_api.py
git commit -m "feat: resolve owning page name for a block uuid"
```

---

## Task 4: Sayfa adı taşıyan okuma araçlarında enforcement

Kapsam: `get_page_content`, `get_page_backlinks`, `get_pages_from_namespace`, `get_pages_tree_from_namespace`.

**Files:**
- Modify: `src/mcp_logseq/tools.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
from mcp_logseq.tools import (
    GetPageContentToolHandler,
    GetPageBacklinksToolHandler,
    GetPagesFromNamespaceToolHandler,
    GetPagesTreeFromNamespaceToolHandler,
)


def _ns(include=None, exclude=None):
    """Patch namespace module config for a test."""
    return patch.multiple(
        "mcp_logseq.tools",
        _include_namespaces=include or [],
        _exclude_namespaces=exclude or [],
        _exclude_tags=[],
    )


def test_get_page_content_denies_excluded_namespace():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            GetPageContentToolHandler().run_tool({"page_name": "finance/q3"})


def test_get_page_content_denies_outside_allowlist():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPageContentToolHandler().run_tool({"page_name": "personal/diary"})


def test_get_page_backlinks_denies():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            GetPageBacklinksToolHandler().run_tool({"page_name": "finance/q3"})


def test_get_pages_from_namespace_denies():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPagesFromNamespaceToolHandler().run_tool({"namespace": "finance"})


def test_get_pages_tree_from_namespace_denies():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            GetPagesTreeFromNamespaceToolHandler().run_tool({"namespace": "finance"})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k "get_page_content_denies or backlinks_denies or from_namespace_denies or tree_from_namespace" -v`
Expected: FAIL (henüz enforcement yok; raise olmaz)

- [ ] **Step 3a: `get_page_content` — mevcut tag kontrolünü namespace ile birleştir**

`src/mcp_logseq/tools.py` satır ~444-449'u şununla değiştir:

```python
            # Security: block access to restricted pages (tag OR namespace) — fail loudly
            if _is_page_blocked(result.get("page", {}), args["page_name"]):
                raise AccessDenied(
                    f"Access denied: page '{args['page_name']}' is restricted "
                    f"and cannot be accessed by this assistant."
                )
```

- [ ] **Step 3b: `get_page_backlinks` — pre-flight enforcement ekle**

`src/mcp_logseq/tools.py` satır ~1662 civarı, `page_name = args["page_name"]` satırından hemen sonra (try bloğundan önce ya da api oluşturmadan önce) ekle:

```python
        page_name = args["page_name"]
        _enforce_namespace_access(page_name)
```

- [ ] **Step 3c: `get_pages_from_namespace` ve `get_pages_tree_from_namespace` — namespace arg'ını kontrol et**

`GetPagesFromNamespaceToolHandler.run_tool` içinde, `api = _make_api()` çağrısından önce ekle:

```python
        _enforce_namespace_access(args["namespace"])
```

`GetPagesTreeFromNamespaceToolHandler.run_tool` içinde de aynı şekilde, `api = _make_api()` çağrısından önce ekle:

```python
        _enforce_namespace_access(args["namespace"])
```

Not: Bu iki handler'ın `run_tool` gövdesinde `namespace` argümanı `args["namespace"]` olarak okunuyor; enforcement satırını fonksiyonun en başına, `try:` varsa onun dışına/öncesine koy ki `AccessDenied` sert hata olarak yükselsin.

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/tools.py tests/unit/test_namespace_access.py
git commit -m "feat: enforce namespace access on page-name read tools"
```

---

## Task 5: Sayfa adı taşıyan yazma/silme araçlarında enforcement

Kapsam: `create_page`, `update_page`, `delete_page`, `rename_page` (hem `old_name` hem `new_name`).

**Files:**
- Modify: `src/mcp_logseq/tools.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
from mcp_logseq.tools import (
    CreatePageToolHandler,
    UpdatePageToolHandler,
    DeletePageToolHandler,
    RenamePageToolHandler,
)


def test_create_page_denies_excluded_namespace():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            CreatePageToolHandler().run_tool({"page_name": "finance/new", "content": "x"})


def test_update_page_denies_outside_allowlist():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            UpdatePageToolHandler().run_tool({"page_name": "personal/x", "content": "y"})


def test_delete_page_denies():
    with _ns(exclude=["finance"]):
        with pytest.raises(AccessDenied):
            DeletePageToolHandler().run_tool({"page_name": "finance/q3"})


def test_rename_page_denies_source():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool({"old_name": "personal/x", "new_name": "work/x"})


def test_rename_page_denies_target():
    with _ns(include=["work"]):
        with pytest.raises(AccessDenied):
            RenamePageToolHandler().run_tool({"old_name": "work/x", "new_name": "personal/x"})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k "create_page_denies or update_page_denies or delete_page_denies or rename_page_denies" -v`
Expected: FAIL

- [ ] **Step 3a: `create_page` enforcement**

`CreatePageToolHandler.run_tool` başında, page name argümanı okunduktan sonra (api oluşturulmadan önce) ekle:

```python
        _enforce_namespace_access(args["page_name"])
```

- [ ] **Step 3b: `update_page` enforcement**

`src/mcp_logseq/tools.py` satır ~626, `page_name = args["page_name"]` satırından hemen sonra ekle:

```python
        page_name = args["page_name"]
        _enforce_namespace_access(page_name)
```

- [ ] **Step 3c: `delete_page` enforcement**

`DeletePageToolHandler.run_tool` başında, `try:` bloğundan önce ekle:

```python
        _enforce_namespace_access(args["page_name"])
```

- [ ] **Step 3d: `rename_page` enforcement (kaynak + hedef)**

`src/mcp_logseq/tools.py` satır ~1608-1609, `old_name`/`new_name` okunduktan hemen sonra ekle:

```python
        old_name = args["old_name"]
        new_name = args["new_name"]
        _enforce_namespace_access(old_name)
        _enforce_namespace_access(new_name)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/tools.py tests/unit/test_namespace_access.py
git commit -m "feat: enforce namespace access on page write/delete tools"
```

---

## Task 6: Block-UUID araçlarında enforcement

Kapsam: `get_block`, `update_block`, `delete_block`, `insert_nested_block`, `set_block_properties`. Her biri `api = _make_api()` sonrası `_enforce_block_namespace_access(api, <uuid>)` çağırır; `AccessDenied` sert hata olarak yükselmeli (generic `except Exception`'a yakalanıp `❌` mesajına dönüşmemeli), bu yüzden her handler'ın generic except'inden ÖNCE `except AccessDenied: raise` eklenir.

**Files:**
- Modify: `src/mcp_logseq/tools.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
from mcp_logseq.tools import (
    GetBlockToolHandler,
    UpdateBlockToolHandler,
    DeleteBlockToolHandler,
    InsertNestedBlockToolHandler,
)


def _api_with_block_page(page_name):
    """Mock _make_api so get_block_page_name returns a fixed page."""
    fake = Mock()
    fake.get_block_page_name.return_value = page_name
    return patch("mcp_logseq.tools._make_api", return_value=fake)


def test_get_block_denies_when_page_excluded():
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"):
        with pytest.raises(AccessDenied):
            GetBlockToolHandler().run_tool({"block_uuid": "u1"})


def test_update_block_denies_outside_allowlist():
    with _ns(include=["work"]), _api_with_block_page("personal/x"):
        with pytest.raises(AccessDenied):
            UpdateBlockToolHandler().run_tool({"block_uuid": "u2", "content": "c"})


def test_delete_block_denies():
    with _ns(exclude=["finance"]), _api_with_block_page("finance/q3"):
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u3"})


def test_insert_nested_block_denies():
    with _ns(include=["work"]), _api_with_block_page("personal/x"):
        with pytest.raises(AccessDenied):
            InsertNestedBlockToolHandler().run_tool(
                {"parent_block_uuid": "u4", "content": "c"}
            )


def test_block_denied_when_page_unresolvable_and_rules_set():
    with _ns(include=["work"]), _api_with_block_page(None):
        with pytest.raises(AccessDenied):
            DeleteBlockToolHandler().run_tool({"block_uuid": "u5"})


def test_block_allowed_when_no_rules():
    fake = Mock()
    fake.get_block_page_name.return_value = None
    fake.delete_block.return_value = {"ok": True}
    with _ns(), patch("mcp_logseq.tools._make_api", return_value=fake):
        result = DeleteBlockToolHandler().run_tool({"block_uuid": "u6"})
        assert "Successfully deleted" in result[0].text
        fake.get_block_page_name.assert_not_called()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k "block_denies or block_denied or block_allowed or nested_block_denies" -v`
Expected: FAIL

- [ ] **Step 3a: `delete_block`**

`DeleteBlockToolHandler.run_tool` (satır ~717) `try:` içindeki `api = _make_api()` satırından sonra enforcement ekle, ve `except Exception` öncesine `except AccessDenied: raise` ekle:

```python
        try:
            api = _make_api()
            _enforce_block_namespace_access(api, block_uuid)
            api.delete_block(block_uuid)

            return [TextContent(
                type="text",
                text=f"✅ Successfully deleted block '{block_uuid}'"
            )]
        except AccessDenied:
            raise
        except ValueError as e:
            return [TextContent(type="text", text=f"❌ Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Failed to delete block: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to delete block '{block_uuid}': {str(e)}"
            )]
```

- [ ] **Step 3b: `update_block`**

`UpdateBlockToolHandler.run_tool` (satır ~769) `api = _make_api()` sonrasına `_enforce_block_namespace_access(api, block_uuid)` ekle ve `except ValueError`'dan önce `except AccessDenied: raise` ekle:

```python
        try:
            api = _make_api()
            _enforce_block_namespace_access(api, block_uuid)
            api.update_block(block_uuid, content)

            return [TextContent(
                type="text",
                text=f"✅ Successfully updated block '{block_uuid}'"
            )]
        except AccessDenied:
            raise
        except ValueError as e:
            return [TextContent(type="text", text=f"❌ Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Failed to update block: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Failed to update block '{block_uuid}': {str(e)}"
            )]
```

- [ ] **Step 3c: `get_block`**

`GetBlockToolHandler.run_tool` (satır ~831) `api = _make_api()` sonrasına ekle, `except ValueError`'dan önce `except AccessDenied: raise` ekle:

```python
        try:
            api = _make_api()
            _enforce_block_namespace_access(api, block_uuid)
            result = api.get_block(block_uuid, include_children=include_children)
```

ve aynı try'ın except zincirine (satır ~863 öncesi):

```python
        except AccessDenied:
            raise
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
```

- [ ] **Step 3d: `insert_nested_block`**

`InsertNestedBlockToolHandler.run_tool` (satır ~1768) `api = _make_api()` sonrasına ekle, `except ValueError`'dan önce `except AccessDenied: raise` ekle:

```python
        try:
            api = _make_api()
            _enforce_block_namespace_access(api, parent_uuid)
            result = api.insert_block_as_child(
                parent_block_uuid=parent_uuid,
                content=content,
                properties=properties,
                sibling=sibling
            )
```

ve except zincirine:

```python
        except AccessDenied:
            raise
        except ValueError as e:
            return [TextContent(type="text", text=f"❌ Error: {str(e)}")]
```

- [ ] **Step 3e: `set_block_properties`**

`SetBlockPropertiesToolHandler.run_tool` (satır ~1849) `api = _make_api()` sonrasına ekle:

```python
        try:
            api = _make_api()
            _enforce_block_namespace_access(api, block_uuid)
            results = []
```

ve bu handler'ın except zincirine (mevcut `except Exception`'dan önce) ekle:

```python
        except AccessDenied:
            raise
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/tools.py tests/unit/test_namespace_access.py
git commit -m "feat: enforce namespace access on block-uuid tools (fail-closed)"
```

---

## Task 7: Liste/arama/query/property filtreleme

Kapsam: `list_pages`, `search` (`_build_excluded_page_names` genişlet), `query`, `find_pages_by_property`. Hepsi sonuç setinden bloklu sayfaları **sessizce** eler.

**Files:**
- Modify: `src/mcp_logseq/tools.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
from mcp_logseq.tools import ListPagesToolHandler, SearchToolHandler, QueryToolHandler


def test_list_pages_hides_blocked_namespace():
    pages = [
        {"originalName": "work/projects", "properties": {}},
        {"originalName": "finance/q3", "properties": {}},
    ]
    fake = Mock()
    fake.list_pages.return_value = pages
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = ListPagesToolHandler().run_tool({})[0].text
        assert "work/projects" in out
        assert "finance/q3" not in out


def test_list_pages_strict_allowlist_hides_unnamespaced():
    pages = [
        {"originalName": "work/projects", "properties": {}},
        {"originalName": "Fikirler", "properties": {}},
    ]
    fake = Mock()
    fake.list_pages.return_value = pages
    with _ns(include=["work"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = ListPagesToolHandler().run_tool({})[0].text
        assert "work/projects" in out
        assert "Fikirler" not in out


def test_search_excludes_blocked_namespace_pages():
    fake = Mock()
    fake.list_pages.return_value = [
        {"originalName": "finance/q3", "properties": {}},
        {"originalName": "work/x", "properties": {}},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        names = SearchToolHandler._build_excluded_page_names(
            fake, [], ["finance"], []
        )
        assert "finance/q3" in names
        assert "work/x" not in names


def test_query_hides_blocked_page_objects():
    fake = Mock()
    fake.query_dsl.return_value = [
        {"originalName": "finance/q3"},
        {"originalName": "work/x"},
    ]
    with _ns(exclude=["finance"]), patch("mcp_logseq.tools._make_api", return_value=fake):
        out = QueryToolHandler().run_tool({"query": "(page-property x)"})[0].text
        assert "work/x" in out
        assert "finance/q3" not in out
```

Not: `_build_excluded_page_names` imzası bu task'ta değişiyor (aşağıda). Test bu yeni imzayı (`api, exclude_tags, exclude_namespaces, include_namespaces`) kullanıyor.

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k "list_pages_hides or strict_allowlist_hides or search_excludes or query_hides" -v`
Expected: FAIL

- [ ] **Step 3a: `list_pages` filtresi**

`src/mcp_logseq/tools.py` satır ~286-288'i değiştir:

```python
                # Security: pages blocked by tag OR namespace are invisible
                name_for_check = page.get("originalName") or page.get("name", "")
                if _is_page_blocked(page, name_for_check):
                    continue
```

- [ ] **Step 3b: `search` — `_build_excluded_page_names` genişlet**

`src/mcp_logseq/tools.py` satır ~916-935'teki staticmethod'u değiştir:

```python
    @staticmethod
    def _build_excluded_page_names(
        api,
        exclude_tags: list[str],
        exclude_namespaces: list[str],
        include_namespaces: list[str],
    ) -> set[str]:
        """Return lowercased names of pages blocked by tag or namespace rules.

        Makes one extra api.list_pages() call when any rule is configured.
        Fails open on error to avoid breaking search entirely.
        """
        if not exclude_tags and not exclude_namespaces and not include_namespaces:
            return set()
        try:
            pages = api.list_pages()
            blocked = set()
            for page in pages:
                name = page.get("originalName") or page.get("name", "")
                if not name:
                    continue
                if _is_page_excluded(page, exclude_tags) or _is_namespace_blocked(
                    name, include_namespaces, exclude_namespaces
                ):
                    blocked.add(name.lower())
            return blocked
        except Exception as e:
            logger.warning(f"Could not build blocked page names for search filtering: {e}")
            return set()
```

Ve çağrı yerini (satır ~1150) güncelle:

```python
            excluded_page_names = self._build_excluded_page_names(
                api, _exclude_tags, _exclude_namespaces, _include_namespaces
            )
```

- [ ] **Step 3c: `query` filtresi**

`src/mcp_logseq/tools.py` satır ~1289-1296'yı değiştir:

```python
            # Security: filter page objects blocked by tag OR namespace
            if _exclude_tags or _include_namespaces or _exclude_namespaces:
                filtered = []
                for item in filtered_results:
                    if self._is_page(item):
                        name = item.get("originalName") or item.get("name", "")
                        if _is_page_excluded(item, _exclude_tags) or _is_namespace_blocked(
                            name, _include_namespaces, _exclude_namespaces
                        ):
                            continue
                    filtered.append(item)
                filtered_results = filtered
```

- [ ] **Step 3d: `find_pages_by_property` filtresi**

`FindPagesByPropertyToolHandler.run_tool` içinde, `limited_results = result[:limit]` satırından ÖNCE (satır ~1414) ham `result` listesini filtrele:

```python
            # Security: drop pages blocked by tag OR namespace before limiting
            if _exclude_tags or _include_namespaces or _exclude_namespaces:
                kept = []
                for item in result:
                    if isinstance(item, dict):
                        name = item.get("originalName") or item.get("name", "")
                        if _is_page_excluded(item, _exclude_tags) or _is_namespace_blocked(
                            name, _include_namespaces, _exclude_namespaces
                        ):
                            continue
                    kept.append(item)
                result = kept

            # Apply limit
            limited_results = result[:limit]
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/tools.py tests/unit/test_namespace_access.py
git commit -m "feat: filter list/search/query/property results by namespace"
```

---

## Task 8: Vektör arama sonuç filtresi

**Files:**
- Modify: `src/mcp_logseq/vector/index.py`
- Test: `tests/unit/test_namespace_access.py`

- [ ] **Step 1: Failing testi yaz**

`tests/unit/test_namespace_access.py` sonuna ekle:

```python
def test_vector_results_filtered_by_namespace():
    from mcp_logseq.vector.index import _filter_results_by_namespace

    class R:
        def __init__(self, page):
            self.page = page

    results = [R("work/x"), R("finance/q3"), R("Fikirler")]
    kept = _filter_results_by_namespace(results, include=["work"], exclude=[])
    pages = [r.page for r in kept]
    assert pages == ["work/x"]  # strict allow-list drops finance and unnamespaced
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k vector_results -v`
Expected: FAIL — `ImportError: cannot import name '_filter_results_by_namespace'`

- [ ] **Step 3: Filtreyi implement et ve aramaya bağla**

`src/mcp_logseq/vector/index.py` importlarına ekle (satır ~23):

```python
from mcp_logseq.tools import (
    ToolHandler,
    _is_namespace_blocked,
    _include_namespaces,
    _exclude_namespaces,
)
```

Modül seviyesinde, `_format_search_results` tanımının (satır ~44) yakınına bir helper ekle:

```python
def _filter_results_by_namespace(results, include, exclude):
    """Drop vector search results whose page is blocked by namespace rules."""
    if not include and not exclude:
        return results
    return [r for r in results if not _is_namespace_blocked(r.page, include, exclude)]
```

`VectorSearchToolHandler.run_tool` içinde, `results = db.search(params)` sonrası ve `output = ...` öncesinde (satır ~213-215 arası) filtreyi uygula:

```python
        results = _filter_results_by_namespace(
            results, _include_namespaces, _exclude_namespaces
        )

        output = output_prefix + _format_search_results(results)
        return [TextContent(type="text", text=output)]
```

Not: `_include_namespaces`/`_exclude_namespaces` `tools.py`'den import edildiği için modül yüklendiğinde sabitlenir. Testler `tools` modülündeki global'leri patch'lediğinden, helper'ı parametreli tuttuk (`include`/`exclude` argüman alıyor) ki test patch'i etkili olsun; `run_tool` çağrısı import edilen değerleri geçer.

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `uv run pytest tests/unit/test_namespace_access.py -k vector_results -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/vector/index.py tests/unit/test_namespace_access.py
git commit -m "feat: filter vector search results by namespace"
```

---

## Task 9: Tüm test paketi + dokümantasyon

**Files:**
- Modify: `CLAUDE.local.md` veya `README` (varsa config bölümü)
- Test: tüm paket

- [ ] **Step 1: Tüm testleri çalıştır**

Run: `uv run pytest -v --tb=short`
Expected: PASS (yeni testler + tüm mevcut testler; özellikle `test_exclude_tags.py` regresyonu)

- [ ] **Step 2: Dokümantasyon güncelle**

Eğer `README.md` içinde config/environment değişkenleri bölümü varsa, şu env değişkenlerini ekle (yoksa bu adımı atla ve sadece `config.py` docstring'i Task 1'de güncellenmiş olur):

```
LOGSEQ_INCLUDE_NAMESPACES  Virgülle ayrılmış allow-list namespace'ler (örn. "work,projects").
                           Ayarlıysa yalnızca bu namespace'ler (ve alt sayfaları) erişilebilir;
                           namespace'siz üst seviye sayfalar dahil gerisi gizlenir.
LOGSEQ_EXCLUDE_NAMESPACES  Virgülle ayrılmış deny-list namespace'ler (örn. "finance,work/secret").
                           Bu namespace'ler her zaman engellenir (include'a göre öncelikli).
```

Konfig dosyası kökünde `include_namespaces` / `exclude_namespaces` anahtarları da (list veya virgüllü string) desteklenir.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: document namespace access control config"
```

---

## Self-Review (yazarken yapıldı)

- **Spec coverage:** Config (Task 1), eşleştirme+öncelik+katmanlar (Task 2), block→page çözümü (Task 3), tüm A-grubu okuma (Task 4) ve yazma/silme (Task 5) araçları, B-grubu block araçları fail-closed (Task 6), C-grubu liste/arama/query/property filtreleme (Task 7), vektör (Task 8). Tüm spec maddeleri bir task'a bağlı.
- **Placeholder taraması:** Yok; her kod adımı tam kod içeriyor.
- **Tip/imza tutarlılığı:** `_namespace_matches`, `_is_namespace_blocked`, `_is_page_blocked`, `_enforce_namespace_access`, `_enforce_block_namespace_access`, `AccessDenied`, `get_block_page_name`, `_get_page_name_by_id`, `_filter_results_by_namespace` adları tüm task'larda tutarlı. `_build_excluded_page_names` yeni imzası (Task 7) hem implementasyon hem testte aynı sırada (`api, exclude_tags, exclude_namespaces, include_namespaces`).
- **Doğrulanan gerçek detaylar:** `rename_page` argümanları `old_name`/`new_name`; `insert_nested_block` argümanı `parent_block_uuid`; vektör sonucu `SearchResult.page`; `vector/index.py` zaten `from mcp_logseq.tools import ToolHandler` yapıyor (döngüsel import yok).

## Kapsam dışı (YAGNI)

- Tag bazlı include (whitelist).
- Per-tool/per-agent farklı politikalar.
- Regex/glob namespace desenleri.
- Yazma araçlarında tag bazlı kontrol (mevcut okuma kapsamı korunur).
