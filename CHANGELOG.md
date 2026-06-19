# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
