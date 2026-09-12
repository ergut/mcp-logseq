# A5 — Logging Configuration and Payload Redaction (Design)

**Date:** 2026-07-19
**Source:** ARCHITECTURE_REVIEW.md item A5 (the last remaining item from the review).

## Problem

- Importing `server.py` calls `logging.basicConfig(level=logging.DEBUG)` on the
  **root logger** and attaches a `FileHandler` writing to
  `~/.cache/mcp-logseq/mcp_logseq.log` at DEBUG. A library/server module must
  not hijack the host process's logging configuration.
- `call_tool` logs every call's full `arguments` at INFO and the full tool
  `result` at DEBUG. Page/block content — including pages the ACL layer is
  meant to gate — ends up on disk in plaintext.

## Design

### 1. Remove import-time logging configuration from `server.py`

Delete the `basicConfig` call and the unconditional file-handler block
(`server.py` lines 16–36). The module keeps only
`logger = logging.getLogger("mcp-logseq")`. No other module needs changes:
`logseq.py`, `config.py`, `access.py`, and the tool handlers already use
`logging.getLogger(...)` without configuring anything.

### 2. Configure logging in the CLI entrypoint (`__init__.main()`)

`main()` is the single entrypoint for both transports (stdio and http), so one
`_setup_logging()` call at its start covers everything:

- **Level** from `LOGSEQ_LOG_LEVEL` (case-insensitive: `DEBUG`, `INFO`,
  `WARNING`, `ERROR`, `CRITICAL`). Default: **INFO**. An invalid value logs a
  warning and falls back to INFO.
- **Stderr handler** via `logging.basicConfig(...)` with the existing format
  string (`%(asctime)s - %(name)s - %(levelname)s - %(message)s`). Configuring
  the root logger is correct at this layer — the CLI owns the process.
- **File logging is opt-in**: only when `LOGSEQ_LOG_FILE=<path>` is set, a
  `FileHandler` for that path is added (same level and format). If the file
  cannot be opened, log a warning and continue with stderr only. The
  unconditional `~/.cache/mcp-logseq/mcp_logseq.log` file is gone.

### 3. Redact payloads at the dispatch choke point (`call_tool`)

`call_tool` in `server.py` is the single dispatch point (the A4 refactor's
choke-point structure), so redaction happens once, there:

- Arguments: log the tool name and the **argument keys only**, after the
  `isinstance(arguments, dict)` check —
  `Tool call: create_page (argument keys: content, title)`.
- Result: log the **count of content items** instead of the bodies —
  `Tool create_page returned 1 content item(s)`.

Identifier-level logs elsewhere (`logseq.py` logging page names, query
strings, block counts) match the review's "log sizes/identifiers instead"
guidance and stay as they are.

### 4. Documentation and changelog

- README "Environment Variables" section: add `LOGSEQ_LOG_LEVEL` and
  `LOGSEQ_LOG_FILE`.
- `CHANGELOG.md` `[Unreleased]`: note the behavior change — no more
  DEBUG-by-default, and no log file is written unless `LOGSEQ_LOG_FILE` is
  set. Anyone relying on `~/.cache/mcp-logseq/mcp_logseq.log` must now opt in.

## Testing

- Unit tests for `_setup_logging()`: default level INFO, `LOGSEQ_LOG_LEVEL`
  honored, invalid value falls back to INFO, `LOGSEQ_LOG_FILE` attaches a file
  handler, unopenable path degrades gracefully.
- A test asserting that importing `mcp_logseq.server` does not touch the root
  logger's level or handlers.
- A test asserting `call_tool` logs argument keys but not argument values
  (e.g. a marker string in `content` must not appear in `caplog.text`).
- Existing `caplog` tests are unaffected: `caplog` captures via its own
  handler, independent of `basicConfig`.

## Error handling

- Invalid `LOGSEQ_LOG_LEVEL` → warning + INFO fallback (never crash).
- Unwritable `LOGSEQ_LOG_FILE` → warning + stderr-only (matches the old
  behavior of continuing without file logging).
