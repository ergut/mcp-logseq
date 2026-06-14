# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
