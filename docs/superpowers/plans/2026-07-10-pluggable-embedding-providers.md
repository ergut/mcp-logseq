# Pluggable Embedding Providers Implementation Plan

> **Goal:** Add OpenAI and OpenAI-compatible embedding providers while
> preserving existing Ollama behavior and vector-index safety.

Design: [Pluggable Embedding Providers](../specs/2026-07-10-pluggable-embedding-providers-design.md)

## Task 1: Extend and validate configuration

**Files:**

- Modify: `src/mcp_logseq/config.py`
- Test: `tests/unit/vector/test_config.py`

- [x] Add failing tests for OpenAI, OpenAI-compatible, provider-specific
  defaults, `api_key`, `dimensions`, and required fields.
- [x] Add optional `api_key` and `dimensions` to `EmbedderConfig`.
- [x] Replace the Ollama-only rejection with provider-specific parsing and
  validation while preserving the loader's never-raise contract.
- [x] Run the affected config tests.

## Task 2: Implement hosted adapter

**Files:**

- Modify: `src/mcp_logseq/vector/embedder.py`
- Test: `tests/unit/vector/test_embedder.py`

- [x] Add failing request/response, validation, error, key, and factory tests.
- [x] Implement `OpenAICompatibleEmbedder` with optional bearer auth and
  requested dimensions.
- [x] Validate and reorder response vectors before exposing them to sync/search.
- [x] Extend `create_embedder()` for `openai` and `openai-compatible`.
- [x] Run the affected embedder tests.

## Task 3: Remove Ollama-only assumptions

**Files:**

- Modify: `src/mcp_logseq/bin/logseq_sync.py`
- Modify: `src/mcp_logseq/vector/sync.py`
- Test: `tests/unit/vector/test_logseq_sync.py`

- [x] Make connection and batching messages provider-neutral.
- [x] Refuse sync and search when configured provider/model/dimensions do not
  match the existing vector index.
- [x] Add a CLI regression test for the selected provider in startup output.
- [x] Run affected CLI and sync tests.

## Task 4: Document configuration and migration behavior

**Files:**

- Modify: `VECTOR_SEARCH.md`
- Modify: `README.md`

- [x] Describe supported provider values and each provider's required fields.
- [x] Add complete Ollama, OpenAI, and OpenAI-compatible examples.
- [x] Document credential handling and the required rebuild after changing
  provider, model, or dimensions.
- [x] Remove wording that claims vector search is Ollama-only or always local.

## Task 5: Validate the branch

- [x] Run Pyright over every modified Python file with no errors.
- [x] Keep the repository-wide Pyright baseline out of scope; scoped checking
  was explicitly approved, and unrelated existing typing errors are unchanged.
- [x] Run `uv build` with no errors.
- [x] Run `uv run pytest tests/unit/` with no failures.
- [x] Review the diff for credentials, unrelated changes, and compatibility.
- [x] Prepare draft GitHub issue and pull-request descriptions without
  publishing them yet.

## GitHub Publication Drafts

### Issue

**Title:** `feat(vector): support OpenAI-compatible embedding providers`

**Body:**

The optional vector-search feature currently accepts only a local Ollama
embedder. Users should be able to select a hosted OpenAI embedding model or any
service implementing the OpenAI embeddings request/response contract.

Proposed configuration extends the existing `vector.embedder` object with
provider-specific `base_url`, `api_key`, and optional `dimensions` fields while
preserving all current Ollama defaults. The implementation should keep the
provider-neutral `Embedder` interface, avoid a new SDK dependency, validate
hosted responses, and refuse searches or incremental syncs when the configured
embedding space does not match the existing vector index.

Acceptance criteria:

- Existing Ollama configurations work without migration or re-indexing.
- `provider: "openai"` uses the OpenAI embeddings API with a required API key.
- `provider: "openai-compatible"` uses a configurable API root and optional
  bearer token.
- Hosted responses are ordered and validated before reaching LanceDB.
- Provider, model, or dimension changes require `logseq-sync --rebuild`.
- API keys are never logged or persisted in sync metadata.
- Documentation explains hosted-provider data flow and credential handling.

### Pull Request

**Title:** `feat(vector): add OpenAI-compatible embedding providers`

**Body:**

## Summary

- add `openai` and `openai-compatible` provider configuration alongside Ollama
- add bearer authentication, optional output dimensions, and strict hosted
  response validation without introducing a new runtime dependency
- guard both sync and search against provider/model/dimension mismatches
- make sync output provider-neutral and document local versus hosted data flow

## Validation

- modified-file Pyright: 0 errors
- unit tests: 576 passed
- package build: source distribution and wheel built successfully

## Known repository baseline

Repository-wide Pyright 1.1.411 currently reports 63 pre-existing errors outside
the feature files. Those are not included in this feature diff and must be
resolved or baselined before claiming a clean repository-wide lint gate.
