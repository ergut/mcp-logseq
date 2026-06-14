<div align="center">
  <img src="assets/images/logo.png" alt="MCP LogSeq" width="200" height="200">
  <h1>MCP server for LogSeq</h1>
  <p>Connect Claude to your LogSeq knowledge base. Read, create, and manage pages — with optional semantic vector search and DB-mode graph support.</p>
</div>

## ✨ What You Can Do

Transform your LogSeq knowledge base into an AI-powered workspace! This MCP server enables Claude to seamlessly interact with your LogSeq graphs.

### 🎯 Real-World Examples

**📊 Intelligent Knowledge Management**
```
"Analyze all my project notes from the past month and create a status summary"
"Find pages mentioning 'machine learning' and create a study roadmap"
"Search for incomplete tasks across all my pages"
```

**📝 Automated Content Creation**
```
"Create a new page called 'Today's Standup' with my meeting notes"
"Add today's progress update to my existing project timeline page"  
"Create a weekly review page from my recent notes"
```

**🔍 Smart Research & Analysis**
```
"Compare my notes on React vs Vue and highlight key differences"
"Find all references to 'customer feedback' and summarize themes"
"Create a knowledge map connecting related topics across pages"
```

**🧠 Semantic Search** *(optional, requires vector setup)*
```
"Find everything I wrote about burnout, even if I didn't use that word"
"What notes relate to my thoughts on deep work?"
"Search across my Dutch and English notes for ideas about productivity"
```

**🤝 Meeting & Documentation Workflow**
```
"Read my meeting notes and create individual task pages for each action item"
"Get my journal entries from this week and create a summary page"
"Search for 'Q4 planning' and organize all related content into a new overview page"
```

### 💡 Key Benefits
- **Zero Context Switching**: Claude works directly with your LogSeq data
- **Preserve Your Workflow**: No need to export or copy content manually
- **Intelligent Organization**: AI-powered page creation, linking, and search
- **Enhanced Productivity**: Automate repetitive knowledge work
- **Semantic Vector Search** *(optional)*: Find notes by meaning using local Ollama embeddings — no data leaves your machine
- **DB-mode Support** *(opt-in)*: Read and write class properties on Logseq DB-mode graphs

---

## 🚀 Quick Start

### Step 1: Enable LogSeq API
1. **Settings** → **Features** → Check "Enable HTTP APIs server"
2. Click the **API button (🔌)** in LogSeq → **"Start server"**
3. **Generate API token**: API panel → "Authorization tokens" → Create new

### Step 2: Add to Claude (No Installation Required!)

#### Claude Code
```bash
claude mcp add mcp-logseq \
  --env LOGSEQ_API_TOKEN=your_token_here \
  --env LOGSEQ_API_URL=http://localhost:12315 \
  -- uv run --with mcp-logseq mcp-logseq
```

#### Claude Desktop
Add to your config file (`Settings → Developer → Edit Config`):
```json
{
  "mcpServers": {
    "mcp-logseq": {
      "command": "uv",
      "args": ["run", "--with", "mcp-logseq", "mcp-logseq"],
      "env": {
        "LOGSEQ_API_TOKEN": "your_token_here",
        "LOGSEQ_API_URL": "http://localhost:12315"
      }
    }
  }
}
```

### Step 3: Start Using!
```
"Please help me organize my LogSeq notes. Show me what pages I have."
```

---

## 🔬 Vector Search (Optional)

Semantic search over your Logseq graph using local AI embeddings — find notes by meaning, not just keywords. Searches across all your pages using vector similarity and full-text search combined, with cross-language support.

Powered by [Ollama](https://ollama.com) (local embeddings) and [LanceDB](https://lancedb.com) (embedded vector DB). No data leaves your machine.

→ **[Full setup guide: VECTOR_SEARCH.md](VECTOR_SEARCH.md)**

---

## 🛠️ Available Tools

The server provides 16 tools with intelligent markdown parsing, plus 3 optional vector search tools:

| Tool | Purpose | Example Use |
|------|---------|-------------|
| **`list_pages`** | Browse your graph | "Show me all my pages" |
| **`get_page_content`** | Read page content | "Get my project notes" |
| **`create_page`** | Add new pages with structured blocks | "Create a meeting notes page with agenda items" |
| **`update_page`** | Modify pages (append/replace modes) | "Update my task list" |
| **`delete_page`** | Remove pages | "Delete the old draft page" |
| **`delete_block`** | Remove a block by UUID | "Delete this specific block" |
| **`update_block`** | Edit block content by UUID | "Update this specific block text" |
| **`search`** | Find content across graph | "Search for 'productivity tips'" |
| **`query`** | Execute Logseq DSL queries | "Find all TODO tasks tagged #project" |
| **`find_pages_by_property`** | Search pages by property | "Find all pages with status = active" |
| **`get_pages_from_namespace`** | List pages in a namespace | "Show all pages under Customer/" |
| **`get_pages_tree_from_namespace`** | Hierarchical namespace view | "Show Projects/ as a tree" |
| **`rename_page`** | Rename with reference updates | "Rename 'Old Name' to 'New Name'" |
| **`get_page_backlinks`** | Find pages linking to a page | "What links to this page?" |
| **`insert_nested_block`** | Insert child/sibling blocks | "Add a child block under this task" |
| **`set_block_properties`** | Set DB-mode class properties on a block | "Set the status of this block to active" *(DB-mode only)* |
| **`vector_search`** ⚗️ | Semantic search by meaning | "Find notes about shadow work or Jung" |
| **`sync_vector_db`** ⚗️ | Sync vector DB with graph files | "Update the search index" |
| **`vector_db_status`** ⚗️ | Show vector DB health and staleness | "Is my search index up to date?" |

⚗️ *Requires vector search setup — see [VECTOR_SEARCH.md](VECTOR_SEARCH.md)*

### 🎨 Smart Markdown Parsing (v1.1.0+)

The `create_page` and `update_page` tools now automatically convert markdown into Logseq's native block structure:

**Markdown Input:**
```markdown
---
tags: [project, active]
priority: high
---

# Project Overview
Introduction paragraph here.

## Tasks
- Task 1
  - Subtask A
  - Subtask B
- Task 2

## Code Example
```python
def hello():
    print("Hello Logseq!")
```
```

**Result:** Creates properly nested blocks with:
- ✅ Page properties from YAML frontmatter (`tags`, `priority`)
- ✅ Hierarchical sections from headings (`#`, `##`, `###`)
- ✅ Nested bullet lists with proper indentation
- ✅ Code blocks preserved as single blocks
- ✅ Checkbox support (`- [ ]` → TODO, `- [x]` → DONE)

**Update Modes:**
- **`append`** (default): Add new content after existing blocks
- **`replace`**: Clear page and replace with new content

### 🔁 Safe Retries & Large Writes

`create_page` fails with a clear error if a page with the same title already exists, instead of letting Logseq silently create numbered duplicates (`Page(1)`, `Page 2`, ...). This makes retries after a timeout safe: if a previous `create_page` call timed out but actually committed, the retry tells you the page exists rather than fragmenting your content across ghost pages.

For large writes, prefer this pattern over one giant `create_page` call:

1. Create the page with little or no content (`create_page` with just the title and properties)
2. Append content in smaller chunks with `update_page` (`mode: append`)
3. Read back with `get_page_content` to verify the result

If you hit the "already exists" error mid-ingest, use `get_page_content` to see what landed, then continue with `update_page` instead of re-creating.

---

## ⚙️ Prerequisites

### LogSeq Setup
- **LogSeq installed** and running
- **HTTP APIs server enabled** (Settings → Features)
- **API server started** (🔌 button → "Start server")  
- **API token generated** (API panel → Authorization tokens)

### System Requirements
- **[uv](https://docs.astral.sh/uv/)** Python package manager
- **MCP-compatible client** (Claude Code, Claude Desktop, etc.)

---

## 🔧 Configuration

### Environment Variables
- **`LOGSEQ_API_TOKEN`** (required): Your LogSeq API token
- **`LOGSEQ_API_URL`** (optional): Server URL (default: `http://localhost:12315`)
- **`LOGSEQ_DB_MODE`** (optional): Set to `true` to enable DB-mode property support. Only for Logseq DB-mode graphs (beta). Markdown/file-based graph users should leave this unset.
- **`LOGSEQ_EXCLUDE_TAGS`** (optional): Comma-separated tags — pages with these tags are hidden from all tools. See [Privacy & Access Control](#-privacy--access-control) below.

### Privacy & Access Control

Pages tagged with excluded tags are completely hidden from AI — they won't appear in listings, searches, or queries, and attempting to read them directly returns an access-denied error.

**Quick setup via env var:**
```bash
LOGSEQ_EXCLUDE_TAGS=private,secret
```

**Via config file** (also used for [vector search](VECTOR_SEARCH.md)):
```json
{
  "logseq_graph_path": "/path/to/your/logseq/pages",
  "exclude_tags": ["private", "secret"]
}
```
Point to it with `LOGSEQ_CONFIG_FILE=/path/to/config.json`.

In your Logseq pages, tag any page you want to protect:
```
tags:: private
```

The exclusion applies to all tools: `list_pages`, `get_page_content`, `search`, `query`, and the optional vector search. If you also use vector search, `exclude_tags` at the root is automatically merged into the vector index exclusion list — private pages are never embedded.

### Alternative Setup Methods

#### Using .env file
```bash
# .env
LOGSEQ_API_TOKEN=your_token_here
LOGSEQ_API_URL=http://localhost:12315
```

#### System environment variables
```bash
export LOGSEQ_API_TOKEN=your_token_here
export LOGSEQ_API_URL=http://localhost:12315
```

---

## 🔍 Verification & Testing

### Test LogSeq Connection
```bash
uv run --with mcp-logseq python -c "
from mcp_logseq.logseq import LogSeq
api = LogSeq(api_key='your_token')
print(f'Connected! Found {len(api.list_pages())} pages')
"
```

### Verify MCP Registration
```bash
claude mcp list  # Should show mcp-logseq
```

### Debug with MCP Inspector
```bash
npx @modelcontextprotocol/inspector uv run --with mcp-logseq mcp-logseq
```

---

## 🐛 Troubleshooting

### Common Issues

#### "LOGSEQ_API_TOKEN environment variable required"
- ✅ Enable HTTP APIs in **Settings → Features**
- ✅ Click **🔌 button** → **"Start server"** in LogSeq
- ✅ Generate token in **API panel → Authorization tokens**
- ✅ Verify token in your configuration

#### "spawn uv ENOENT" (Claude Desktop)
Claude Desktop can't find `uv`. Use the full path:

```bash
which uv  # Find your uv location
```

Update config with full path:
```json
{
  "mcpServers": {
    "mcp-logseq": {
      "command": "/Users/username/.local/bin/uv",
      "args": ["run", "--with", "mcp-logseq", "mcp-logseq"],
      "env": { "LOGSEQ_API_TOKEN": "your_token_here" }
    }
  }
}
```

**Common uv locations:**
- Curl install: `~/.local/bin/uv`
- Homebrew: `/opt/homebrew/bin/uv` 
- Pip install: Check with `which uv`

#### Connection Issues
- ✅ Confirm LogSeq is running
- ✅ Verify API server is **started** (not just enabled)
- ✅ Check port 12315 is accessible
- ✅ Test with verification command above

---

## 👩‍💻 Development

For local development, testing, and contributing, see **[DEVELOPMENT.md](DEVELOPMENT.md)**.

---

<div align="center">
  <p><strong>Ready to supercharge your LogSeq workflow with AI?</strong></p>
  <p>⭐ <strong>Star this repo</strong> if you find it helpful!</p>
</div>