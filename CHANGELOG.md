# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.9.1] - 2026-09-13

### Fixed

- `logseq-sync` no longer aborts the whole run when a page is deleted or
  renamed while the sync is in progress. A file that vanishes before hashing
  is skipped and picked up next run; one that vanishes during embedding is
  treated as deleted. Previously a single missing file threw away all
  embedding work of that run and left the index stale (#99, closes #91)
- `search` exclusion filtering in DB mode now fails closed: a page result
  with neither `fullTitle` nor `title` is hidden when `exclude_tags` or
  namespace rules are active, instead of leaking through via `content`.
  Text and JSON output share the same check (#99, closes #57)

### Changed

- `_acquire_sync_lock` raises `RuntimeError` on a lock conflict instead of
  calling `sys.exit`; the CLI entrypoint decides to exit (#99, closes #37)
- The sdist now ships only `src/` (plus README, LICENSE and pyproject), down
  from 1.5 MB to about 72 KB. Tests, docs, `uv.lock` and stray working-tree
  files are no longer packaged (#99)

## [1.9.0] - 2026-09-13

### Added

- Embedding provider API keys can be read from an environment variable via
  `vector.embedder.api_key_env`, so the key never has to be written to
  `config.json`. Plaintext `api_key` keeps working (#82, closes #81, by
  ericfitz)
- `vector.max_chunk_length` (default `10000`): blocks longer than this are
  skipped at chunk time instead of being sent to the embedder, which rejected
  them with a 400 (#97, closes #76)

### Changed

- **Breaking (dependency):** the server now requires `mcp>=2.0,<3` and is ported to the 2.x low-level API, which replaced the `@server.list_tools()` / `@server.call_tool()` decorators with constructor-based handler registration. Environments pinned to `mcp<2` must upgrade (#92)

- **Potentially breaking:** `LogSeq(...)` now defaults `verify_ssl=True` (was
  `False`), so the safe path is the default. The bundled server is unaffected
  (it always sets `verify_ssl` explicitly from the protocol), but external code
  constructing the client directly against a self-signed HTTPS Logseq endpoint
  must now pass `verify_ssl=False` explicitly (#89)
- **Potentially breaking:** logging is no longer configured at import time and
  the server no longer writes `~/.cache/mcp-logseq/mcp_logseq.log` by default.
  The CLI entrypoint now configures stderr logging at `INFO` (was `DEBUG`),
  tunable via `LOGSEQ_LOG_LEVEL`; file logging is opt-in via `LOGSEQ_LOG_FILE`.
  Tool arguments and results are redacted from logs — only tool names, argument
  keys, and result sizes are recorded, so page/block content (including
  ACL-gated pages) no longer lands in plaintext logs

### Fixed

- The server no longer crashes on import with `'Server' object has no attribute 'list_tools'` (surfacing client-side as `MCP error -32000: Connection closed`) when mcp 2.x is installed (#92)
- Tool-call failures still reach the model as in-band error results, and tool arguments are still validated against each tool's `inputSchema` — the 2.x low-level server does neither on a handler's behalf, so the server does both itself (#92)
- Block uuids survive a page rewrite. `update_page` in replace mode used to
  mint fresh uuids for every block, leaving `((uuid))` references elsewhere in
  the graph dangling; `insertBatchBlock` is now called with `keepUUID` (only
  when every id parses as an RFC 4122 uuid, since Logseq silently discards the
  whole batch on a malformed one) and the first block no longer bypasses the
  batch (#93, by sleeyax)
- A failed embedding batch is retried one chunk at a time, so a single
  rejected block no longer drops the other chunks in its batch (#97)

### Documentation

- README: Codex CLI (#94, by sqzhang-jeremy) and OpenCode (#95, from #73 by
  extrospective) client setup sections
- VECTOR_SEARCH.md: how to index multiple graphs (#96, closes #75)

### Internal

- Tech-debt cleanup: migrate off the deprecated LanceDB `table_names()`, commit
  `uv.lock` for reproducible installs, remove dead code (`_get_page_properties`,
  the `remove_block` alias), and unify the duplicated list-parser logic (#89)

## [1.8.0] - 2026-06-19

### Added

- **HTTP/SSE transport** — run the server as a networked service with `--transport http`, secured by bearer-token auth (`MCP_HTTP_AUTH_TOKEN`). A sandboxed or remote client can now reach Logseq over the network with no filesystem mount or direct Logseq-API access, turning the namespace/tag access control into a real server-side security boundary (#69)
- **Per-profile multi-instance serving** — run one process per profile (a shared data config file + a per-process env block of namespace/tag/token + its own port). Adds `--read-only` to disable all write tools, and tag-on-write guards so writes can't land on a tag-excluded page (#69)
- **Native TLS** — `--tls-cert`/`--tls-key` serve HTTPS directly (uvicorn `ssl_certfile`/`ssl_keyfile`), plus a bind guardrail that refuses non-loopback plain-HTTP binds unless you pass `--insecure` (#71)
- New deployment guide at [docs/SERVING.md](docs/SERVING.md) — security model, the per-profile pattern, the separate `logseq-sync` writer, and TLS / reverse-proxy setup

### Changed

- `sync_vector_db` is now inert — the vector DB is owned by a single external `logseq-sync` writer process; the tool points operators at it instead of spawning a sync (#69)

### Fixed

- Block-level results from `search` (DB mode) and `query` (tag-only profiles) are now resolved to their owning page and filtered by the namespace/tag ACL, closing cases where restricted block content could surface in block-level results (#69)
- The page-exclusion set now fails closed when ACL rules are active — if it can't be built, `search` returns an error instead of unfiltered results (#69)

## [1.7.0] - 2026-06-14

### Added

- **Namespace-based access control** — restrict MCP tool access to specific Logseq namespaces via `LOGSEQ_INCLUDE_NAMESPACES` and `LOGSEQ_EXCLUDE_NAMESPACES` environment variables (#65)
- **JSON output format for `query` and `search` tools** — pass `format=json` to get raw result objects including block UUIDs and page identifiers for deep linking (#56)
- **Configurable API timeout** — set `LOGSEQ_API_TIMEOUT` environment variable to override the default 30-second timeout for Logseq API calls (#47) — thanks @thisdotrob

### Fixed

- `create_page` now fails on existing pages instead of silently creating numbered duplicates (e.g. `Page (1)`); retries are safe (#59)
- `update_page` property handling is now graph-type aware, correctly serializing properties for both file-mode and DB-mode graphs (#62)
- Inline `key:: value` properties are now correctly attached to their parent list item instead of being treated as top-level blocks (#61) — thanks @sehgalmayank001

## [1.6.3] - 2025-04-12

See [GitHub releases](https://github.com/ergut/mcp-logseq/releases) for earlier history.
