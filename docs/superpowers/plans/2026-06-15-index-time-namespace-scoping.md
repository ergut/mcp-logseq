# Index-Time Namespace Scoping for the Vector DB

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the vector-DB writer scope *what gets embedded at all* by namespace, via `vector.include_namespaces` / `vector.exclude_namespaces` in the config — symmetric with the existing index-time `vector.exclude_tags`. Content irrelevant or off-limits to **every** consumer is then never embedded: smaller DB, less sync compute, faster search.

**Transport-independent:** This feature lives entirely in the sync writer (`config.py` + `chunker.py`), executed by the `logseq-sync` CLI. It has nothing to do with how the MCP server is reached, so it benefits **stdio and HTTP equally**. It is split out of the [secure HTTP serving plan](2026-06-14-http-transport-secure-serving.md) precisely because it stands alone.

---

## Two-axis model (context)

ACL over the vector DB operates on two distinct axes — this feature adds the namespace dimension to the **index-time** axis, which currently only has tags:

| | Index-time (writer global policy) | Query-time (per-consumer) |
|---|---|---|
| **Tags** | `vector.exclude_tags` (exists) | `_exclude_tags` (exists) |
| **Namespace** | **this feature** | `_include_namespaces` / `_exclude_namespaces` (exists) |

Index-time = "what the DB contains," decided once by the writer. Query-time = "what a given consumer sees," decided per request/instance. They compose: anything excluded at index time is gone for everyone; query-time differentiates within what remains.

**Use cases:**
- Whole vault is large but every consumer only cares about one area → `include_namespaces: ["Work"]` indexes only `Work/*`.
- A namespace no consumer should ever vector-search → `exclude_namespaces: ["Secret"]` keeps it out of the DB entirely (stronger than query-time filtering, which leaves the plaintext on disk).

---

## What already exists (reuse, do not rebuild)

- `vector.exclude_tags` index-time filtering in `chunk_file` ([chunker.py:133-135](../../../src/mcp_logseq/vector/chunker.py#L133-L135)) — the exact pattern to mirror (early `return []`).
- `page_title` derivation incl. the `___` → `/` namespace separator ([chunker.py:87-98](../../../src/mcp_logseq/vector/chunker.py#L87-L98)).
- `_is_namespace_blocked` allow/deny semantics (exclude wins; include is a strict allow-list) in `tools.py` — reuse the same logic so index-time and query-time behave identically. Factor the matcher into a small shared helper rather than duplicating.

---

## Tasks

### Task 1: Config fields

**Files:**
- Modify: `src/mcp_logseq/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests** — `load_vector_config` returns a `VectorConfig` whose `include_namespaces` / `exclude_namespaces` reflect the `vector` block; default to `[]` when absent.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** — add `include_namespaces: list[str] = field(default_factory=list)` and `exclude_namespaces: list[str] = field(default_factory=list)` to `VectorConfig`; parse both from `vector_raw` in `load_vector_config` (accept list or comma string, mirroring how root-level CSV configs are normalized).
- [ ] **Step 4: Run to verify pass. Commit** — `git commit -m "feat(config): vector index-time namespace fields"`

### Task 2: Chunker filter

**Files:**
- Modify: `src/mcp_logseq/vector/chunker.py`
- (Optionally) Modify: `src/mcp_logseq/tools.py` to export the namespace matcher for reuse.
- Test: `tests/unit/test_chunker.py`

- [ ] **Step 1: Write failing tests** — with `exclude_namespaces=["Journal"]`, `chunk_file` returns `[]` for a `Journal/*` page; with `include_namespaces=["Work"]`, only `Work/*` pages produce chunks; a page outside the include list yields `[]`. Cover the `___`-encoded namespace filename form too.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** — after `page_title` is derived in `chunk_file`, apply the shared allow/deny matcher against `config.include_namespaces` / `config.exclude_namespaces`; `return []` when blocked, right alongside the existing `exclude_tags` early-return.
- [ ] **Step 4: Run to verify pass. Commit** — `git commit -m "feat(vector): index-time include/exclude namespace scoping"`

### Task 3: Docs + rebuild note

**Files:**
- Modify: `README.md` (or the vector/config docs)

- [ ] **Step 1:** Document the two new `vector` keys and the two-axis model. **Call out:** changing the index policy only takes effect on a full re-index — incremental sync skips unchanged files by content hash, so run `logseq-sync --rebuild` after editing `include_namespaces` / `exclude_namespaces`.
- [ ] **Step 2: Commit** — `git commit -m "docs: index-time namespace scoping + rebuild note"`

---

## Acceptance

- [ ] With `exclude_namespaces=["Secret"]`, after `--rebuild`, `vector_search` returns no `Secret/*` chunk for **any** consumer (absent from the DB, not merely filtered).
- [ ] With `include_namespaces=["Work"]`, only `Work/*` content is searchable.
- [ ] Empty/default config indexes everything (no behavior change for existing setups).
- [ ] `vector_db_status` chunk/page counts drop accordingly after a scoped rebuild.
