# Pluggable Embedding Providers

**Date:** 2026-07-10  
**Status:** Approved by request; implementation follows this design

## Goal

Allow vector search to use hosted embedding services instead of requiring a
local Ollama process. Preserve every existing Ollama configuration and keep the
provider boundary small enough that future, non-compatible APIs can be added as
adapters rather than changing the sync and search code.

The first increment supports three provider values:

- `ollama` — the existing local `POST /api/embed` integration.
- `openai` — OpenAI's hosted `POST /v1/embeddings` API.
- `openai-compatible` — any service exposing the same request and response
  shape, with a configurable base URL and optional bearer token.

## Decisions

1. **Keep the existing `Embedder` interface.** Sync and query code already
   depend only on `embed()`, `dimensions`, and `key`; provider selection remains
   in `create_embedder()`.
2. **Use direct HTTP through the existing `requests` dependency.** Adding an SDK
   for one small endpoint would increase install size and couple the project to
   a vendor-specific client without improving the abstraction.
3. **Add provider credentials to the existing JSON config.** `api_key` is read
   only from `vector.embedder`; it is never logged, included in exceptions, or
   stored in vector sync metadata.
4. **Support an optional requested dimension.** `dimensions` is sent by the
   OpenAI-compatible adapter when configured and becomes part of the embedder
   identity because changing vector size requires a full rebuild.
5. **Validate hosted responses at the boundary.** The adapter sorts results by
   response `index`, then checks result count, index uniqueness, numeric vectors,
   non-empty vectors, and consistent dimensions before returning them.
6. **Preserve Ollama defaults and identity.** Existing configs continue to use
   `nomic-embed-text`, `http://localhost:11434`, and keys such as
   `ollama/nomic-embed-text`.
7. **Treat provider/model/dimensions changes as index changes.** Sync and search
   both compare the configured embedder identity and dimensions with index
   metadata and require `logseq-sync --rebuild` on a mismatch. API key rotation
   and base-URL proxy changes do not change the key.

## Configuration

### Existing Ollama configuration

No migration is required:

```json
{
  "vector": {
    "enabled": true,
    "embedder": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "base_url": "http://localhost:11434"
    }
  }
}
```

### OpenAI

```json
{
  "vector": {
    "enabled": true,
    "embedder": {
      "provider": "openai",
      "model": "text-embedding-3-small",
      "api_key": "replace-with-your-api-key",
      "dimensions": 1536
    }
  }
}
```

`base_url` defaults to `https://api.openai.com/v1`. `model` defaults to
`text-embedding-3-small`. `api_key` is required.

### OpenAI-compatible service

```json
{
  "vector": {
    "enabled": true,
    "embedder": {
      "provider": "openai-compatible",
      "model": "provider-model-name",
      "base_url": "https://embeddings.example.com/v1",
      "api_key": "replace-if-required"
    }
  }
}
```

Both `model` and `base_url` are required. `api_key` is optional so the adapter
also works with unauthenticated local OpenAI-compatible servers.

| Field | Ollama | OpenAI | OpenAI-compatible |
| --- | --- | --- | --- |
| `provider` | `ollama` | `openai` | `openai-compatible` |
| `model` | optional; defaults to `nomic-embed-text` | optional; defaults to `text-embedding-3-small` | required |
| `base_url` | optional; defaults to local Ollama | optional; defaults to OpenAI | required |
| `api_key` | ignored | required | optional |
| `dimensions` | ignored | optional | optional |

Because `config.json` may now contain a credential, documentation must tell
users not to commit or share it and to restrict its filesystem permissions.

## Request and Response Contract

The hosted adapter sends:

```http
POST {base_url}/embeddings
Authorization: Bearer {api_key}
Content-Type: application/json

{"model": "...", "input": ["..."], "encoding_format": "float"}
```

`dimensions` is included only when configured. A missing API key omits the
`Authorization` header for `openai-compatible`; official `openai` configuration
rejects a missing key before making a request.

The adapter reads `data[].embedding` and restores input order with
`data[].index`. This follows the current OpenAI embeddings API contract:
<https://developers.openai.com/api/reference/resources/embeddings/methods/create>.

## Error Model

- Connection, timeout, and HTTP failures become provider-specific
  `RuntimeError` messages consistent with the existing Ollama adapter.
- Invalid JSON or malformed embedding results fail the whole batch. The sync
  engine retains its existing behavior of logging and skipping a failed batch.
- Error messages include provider and endpoint context but never request
  headers, payload credentials, or `api_key`.
- A configured dimension that differs from the returned vector size is a hard
  error.

## Backward Compatibility

- `provider` still defaults to `ollama`.
- Existing Ollama model and base-URL defaults are unchanged.
- No new runtime dependency is added.
- Existing vector databases keep the same Ollama embedder key and do not require
  rebuilding.
- Switching provider, model, or configured dimensions triggers the existing
  rebuild-required error before incremental sync modifies the database.

## Test Strategy

- Config tests for provider defaults, hosted fields, required fields, unknown
  providers, and Ollama regression behavior.
- Adapter tests for URL, bearer auth, payload, ordering, dimension detection,
  configured dimensions, empty input, missing key, network/HTTP errors, empty or
  malformed responses, and provider factory dispatch.
- CLI test to ensure startup messaging is provider-neutral.
- Existing sync mismatch tests continue to cover rebuild enforcement.
- Full `pyright`, package build, and unit test suite before handoff.

## Out of Scope

- Provider APIs that do not implement the OpenAI embeddings contract, such as
  bespoke Cohere or cloud-platform deployment paths. They can be added later as
  new `Embedder` implementations.
- Retry/backoff and rate-limit scheduling.
- Environment-variable interpolation inside JSON values.
- Automatic migration or rebuilding of an existing vector database.
