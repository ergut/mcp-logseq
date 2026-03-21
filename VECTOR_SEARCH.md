# Vector Search Setup Guide

Semantic search over your Logseq graph using local AI embeddings. Find notes by meaning rather than exact keywords — works across languages and concepts.

## How It Works

1. Your `.md` files are read directly from disk (not via the Logseq API)
2. Each page is chunked into blocks and embedded using a local Ollama model
3. Embeddings are stored in a [LanceDB](https://lancedb.com) database on your machine
4. `vector_search` queries combine vector similarity + full-text search with RRF reranking
5. When your notes change, an incremental sync re-embeds only the changed files

No data leaves your machine. Ollama and LanceDB both run locally.

---

## Prerequisites

### 1. Ollama

Install Ollama from [ollama.com](https://ollama.com) and pull an embedding model:

```bash
ollama pull qwen3-embedding:8b   # recommended — high quality, 4096 dims
# or
ollama pull nomic-embed-text     # lighter alternative
```

Confirm it's running:

```bash
curl http://localhost:11434/api/embed -d '{"model":"qwen3-embedding:8b","input":["test"]}'
```

### 2. Vector extras

Install the optional vector dependencies. The `[vector]` extra pulls in LanceDB, PyArrow, and watchdog.

**From PyPI (once released):**
```bash
uv pip install "mcp-logseq[vector]"
```

**From source (development):**
```bash
cd /path/to/mcp-logseq-server
uv pip install -e ".[vector]"
```

---

## Configuration

Create a JSON config file (e.g. `~/.logseq-vector-config.json`):

```json
{
  "logseq_graph_path": "~/Library/Mobile Documents/iCloud~com~logseq~logseq/Documents",
  "vector": {
    "enabled": true,
    "db_path": "~/.logseq-vector-db",
    "embedder": {
      "provider": "ollama",
      "model": "qwen3-embedding:8b",
      "base_url": "http://localhost:11434"
    },
    "include_journals": true,
    "exclude_tags": ["private"],
    "min_chunk_length": 50
  }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `logseq_graph_path` | ✅ | Path to your Logseq graph directory (contains `pages/` and `journals/`) |
| `vector.enabled` | ✅ | Must be `true` to activate vector tools |
| `vector.db_path` | ✅ | Where to store the vector DB (recommend a local non-iCloud path) |
| `vector.embedder.model` | ✅ | Ollama model name — must match what you pulled |
| `vector.include_journals` | no | Index journal pages (default: `true`) |
| `vector.exclude_tags` | no | Skip pages with these tags (default: `[]`) |
| `vector.min_chunk_length` | no | Minimum characters per chunk (default: `50`) |

### DB path placement

Store the vector DB locally, **not** inside your iCloud-synced graph folder. The DB is a generated binary artifact — syncing it to iCloud wastes bandwidth and can cause corruption.

Good: `~/.logseq-vector-db`
Avoid: `~/Library/Mobile Documents/.../vector-db`

---

## MCP Server Setup

Point the MCP server at your config file via the `LOGSEQ_CONFIG_FILE` environment variable.

### Claude Code

```bash
claude mcp add-json mcp-logseq '{
  "command": "uv",
  "args": ["run", "--with", ".[vector]", "python", "-c", "from mcp_logseq import main; main()"],
  "cwd": "/path/to/mcp-logseq-server",
  "env": {
    "LOGSEQ_API_TOKEN": "your_token",
    "LOGSEQ_API_URL": "http://localhost:12315",
    "LOGSEQ_CONFIG_FILE": "/Users/you/.logseq-vector-config.json"
  }
}' -s local
```

### Claude Desktop

```json
{
  "mcpServers": {
    "mcp-logseq": {
      "command": "uv",
      "args": ["run", "--with", ".[vector]", "python", "-c", "from mcp_logseq import main; main()"],
      "cwd": "/path/to/mcp-logseq-server",
      "env": {
        "LOGSEQ_API_TOKEN": "your_token",
        "LOGSEQ_API_URL": "http://localhost:12315",
        "LOGSEQ_CONFIG_FILE": "/Users/you/.logseq-vector-config.json"
      }
    }
  }
}
```

If `LOGSEQ_CONFIG_FILE` is not set or `vector.enabled` is `false`, the vector tools are silently not registered. All other tools work normally.

---

## First Sync

Before using `vector_search`, you need to build the initial index. This can take several minutes depending on the size of your graph and your embedding model.

```bash
export LOGSEQ_CONFIG_FILE=~/.logseq-vector-config.json
uv run logseq-sync --once
```

You'll see progress as batches of pages are embedded. Check status when done:

```bash
uv run logseq-sync --status
```

---

## Talking to Claude

These tools are called by Claude on your behalf — you don't invoke them directly. Just talk naturally:

```
"Find my notes about shadow work or Jung"
"Search for meeting notes with action items from last week"
"What did I write about machine learning?"
"Is my search index up to date?"
"Sync the vector DB"
"Rebuild the search index from scratch"
```

---

## MCP Tools Reference

Once the server is restarted with `LOGSEQ_CONFIG_FILE` set, three new tools are available to Claude.

### `vector_search`

Semantic search across your notes. Claude calls this when you ask it to find notes by topic, concept, or meaning.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `query` | string | required | Natural language query |
| `top_k` | integer | 5 | Number of results (max 20) |
| `search_mode` | string | `hybrid` | `hybrid`, `vector`, or `keyword` |
| `filter_tags` | array | — | Only return pages with ALL these tags |
| `filter_page` | string | — | Restrict to a single page |

**Auto-sync:** If your graph has changed files since the last sync, `vector_search` automatically starts a background sync and returns current results immediately. The next search will benefit from the updated index.

### `sync_vector_db`

Triggers an incremental sync — only changed files are re-embedded. Claude calls this when you ask it to update or sync the search index.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `rebuild` | boolean | `false` | Drop and re-index everything from scratch |

Ask Claude `"rebuild the search index"` if you change your embedding model.

### `vector_db_status`

Shows the current state of the vector DB. Claude calls this when you ask whether the index is up to date.

```text
Vector DB Status
  Embedder:     ollama/qwen3-embedding:8b
  Dimensions:   4096
  Total chunks: 1203
  Total pages:  461
  Last sync:    2026-03-21T11:21:18Z
  Staleness:    Up to date
```

---

## CLI: `logseq-sync`

For syncing outside of the MCP server — useful for initial indexing, automation, or continuous watch mode.

```bash
export LOGSEQ_CONFIG_FILE=~/.logseq-vector-config.json

logseq-sync --once      # incremental sync and exit
logseq-sync --watch     # sync on file changes (uses watchdog, runs until Ctrl+C)
logseq-sync --rebuild   # drop DB and re-index everything from scratch
logseq-sync --status    # staleness report, no sync
```

For continuous sync without the MCP auto-trigger, `--watch` is the recommended approach. It debounces file system events and re-embeds only changed files.

---

## Troubleshooting

### Vector tools not appearing

- Confirm `LOGSEQ_CONFIG_FILE` is set in the MCP server env
- Confirm `vector.enabled: true` in the config file
- Check the server log: `~/.cache/mcp-logseq/mcp_logseq.log`
- Look for: `Vector search tools registered (3 tools)`

### "Cannot connect to Ollama"

- Confirm Ollama is running: `ollama list`
- Confirm the model is downloaded: `ollama pull qwen3-embedding:8b`
- Check `base_url` in config matches your Ollama address

### Embedder mismatch error on sync

If you change the `model` in your config after an initial sync:

```bash
logseq-sync --rebuild
```

This drops the existing DB and re-indexes from scratch with the new model.

### Slow first sync

Large graphs with `qwen3-embedding:8b` take ~20s per batch of 32 chunks. A graph with 500 pages typically takes 15–30 minutes. Subsequent incremental syncs are much faster — only changed files are re-embedded.

### Pages missing from results

Run `vector_db_status` to check chunk and page counts. If a page is missing, it may have been skipped due to:
- All chunks being under `min_chunk_length`
- The page having a tag listed in `exclude_tags`
- A timeout during the initial sync (run `--once` again to pick it up)
