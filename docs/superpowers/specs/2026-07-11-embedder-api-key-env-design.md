# Design: env-var source for embedding provider API key

**Date:** 2026-07-11
**Issue:** [ergut/mcp-logseq#81](https://github.com/ergut/mcp-logseq/issues/81)
**Status:** Approved

## Problem

The embedding provider `api_key` (introduced in PR #78) lives in plaintext in
`config.json`, mitigated only by documented `chmod 600` guidance. Every other
secret in this project (`LOGSEQ_API_TOKEN`, `MCP_HTTP_AUTH_TOKEN`) is supplied
via environment variable and never written to disk. Support an env-var source
for the embedder key so the plaintext value is no longer required.

## Decision summary

- **Mechanism:** new optional `api_key_env` string field in `vector.embedder`,
  naming the environment variable to read (e.g. `"api_key_env": "OPENAI_API_KEY"`).
  Chosen over a well-known `LOGSEQ_EMBEDDER_API_KEY` variable because it lets
  users point at keys they already export and gives HTTP multi-profile
  deployments per-profile keys.
- **Error mode:** on a named-but-unset variable with no fallback, follow the
  vector loader's never-raise contract — log a clear warning naming the
  variable and disable vector tools (`load_vector_config` returns `None`).

## Config schema

`vector.embedder` gains one optional field:

```json
"embedder": {
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key_env": "OPENAI_API_KEY"
}
```

`EmbedderConfig` is unchanged: the variable is resolved at config-load time and
the resulting secret is stored in the existing `api_key` field. `api_key_env`
is not retained on the dataclass; nothing downstream of `load_vector_config`
changes.

## Resolution semantics

All logic lives in `load_vector_config` in `src/mcp_logseq/config.py`. An env
value that is unset or blank (empty/whitespace after strip) is treated as
"unset."

| `api_key_env` | Named variable | Plaintext `api_key` | Result |
|---|---|---|---|
| absent | — | any | Today's behavior, unchanged (back-compat) |
| valid name | set, non-blank | any | Use env value; it trumps plaintext |
| valid name | unset/blank | present | Warn that the variable is unset; fall back to plaintext key |
| valid name | unset/blank | absent | Warn (name the variable, say how to fix); return `None` (vector disabled) |
| not a non-empty string | — | any | Config error: warn + return `None` |

Notes:

- The unset-with-no-fallback rule applies to `openai-compatible` too, even
  though that provider allows keyless operation: naming a variable signals
  intent to authenticate, so we do not silently proceed unauthenticated.
- The existing "provider `openai` requires `api_key`" check runs after
  resolution, so `api_key_env` alone satisfies it.
- The resolved key is never logged.

## Documentation

- `VECTOR_SEARCH.md`: add `api_key_env` to the OpenAI and openai-compatible
  examples and the options table; recommend the env-var path over plaintext
  `api_key`; keep the `chmod 600` guidance for plaintext holdouts.
- `src/mcp_logseq/config.py` module docstring: update the example config.

## Testing

Unit tests in `tests/unit/vector/test_config.py` (using `monkeypatch`
`setenv`/`delenv`), one per resolution branch:

1. `api_key_env` set, variable present → key comes from env.
2. Both `api_key_env` (variable present) and plaintext `api_key` → env wins.
3. `api_key_env` set, variable unset, plaintext present → plaintext fallback used.
4. `api_key_env` set, variable unset, no fallback → returns `None` (openai and
   openai-compatible variants).
5. `api_key_env` set, variable set to whitespace → treated as unset.
6. `api_key_env` wrong type (e.g. number) or empty string → returns `None`.
7. Regression: plaintext-only config loads identically to today.
8. Provider `openai` with `api_key_env` only (no plaintext) passes the
   requires-a-key check.

## Scope

Touched: `src/mcp_logseq/config.py`, `VECTOR_SEARCH.md`,
`tests/unit/vector/test_config.py`. Untouched: `embedder.py`, `sync.py`,
`index.py`, and all vector runtime code.
