<div align="center">
  <img src="assets/images/logo.png" alt="MCP LogSeq" width="200" height="200">
  <h1>MCP server for LogSeq</h1>
  <p>MCP server to interact with LogSeq via its API. Enables Claude to read, create, and manage LogSeq pages through a comprehensive set of tools.</p>
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

## 🛠️ Available Tools

The server provides 6 comprehensive tools with intelligent markdown parsing:

| Tool | Purpose | Example Use |
|------|---------|-------------|
| **`list_pages`** | Browse your graph | "Show me all my pages" |
| **`get_page_content`** | Read page content | "Get my project notes" |
| **`create_page`** | Add new pages with structured blocks | "Create a meeting notes page with agenda items" |  
| **`update_page`** | Modify pages (append/replace modes) | "Update my task list" |
| **`delete_page`** | Remove pages | "Delete the old draft page" |
| **`search`** | Find content across graph | "Search for 'productivity tips'" |

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