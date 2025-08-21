# MCP server for LogSeq

MCP server to interact with LogSeq via its API. Enables Claude to read, create, and manage LogSeq pages through a comprehensive set of tools.

## Prerequisites

### LogSeq Setup
1. **Install LogSeq** if not already installed
2. **Enable HTTP APIs server** in LogSeq:
   - Go to Settings → Features
   - Check "Enable HTTP APIs server"
3. **Start the API server**:
   - Look for the API button (🔌) in the main LogSeq interface
   - Click it to open the API control panel
   - Click "Start server" to start the HTTP API server at `http://localhost:12315`
4. **Generate API token**:
   - In the API control panel, click "Authorization tokens"
   - Create a new token (e.g., name it "logseq" or "claude")
   - Copy the generated token for use in configuration

### System Requirements
- Python 3.11 or higher
- LogSeq running with HTTP API enabled
- An MCP client (instructions provided for Claude Code and Claude Desktop)

## Installation

This MCP server works with any MCP-compatible client. Below are setup instructions for the most common clients:

### Claude Code

```bash
# Install the package
pip install mcp-logseq

# Add to Claude Code
claude mcp add mcp-logseq \
  --env LOGSEQ_API_TOKEN=your_token_here \
  --env LOGSEQ_API_URL=http://localhost:12315 \
  -- mcp-logseq
```

### Claude Desktop

1. **Install the package**:
```bash
pip install mcp-logseq
```

2. **Open Claude Desktop configuration**:
   - **macOS**: Claude Desktop → Settings → Developer → "Edit Config"
   - **Windows**: Navigate to `%APPDATA%\Claude\claude_desktop_config.json`

3. **Add server configuration**:
```json
{
  "mcpServers": {
    "mcp-logseq": {
      "command": "mcp-logseq",
      "env": {
        "LOGSEQ_API_TOKEN": "your_token_here",
        "LOGSEQ_API_URL": "http://localhost:12315"
      }
    }
  }
}
```

4. **Restart Claude Desktop** for changes to take effect

### Other MCP Clients

For other MCP clients, use the server command `mcp-logseq` with these environment variables:
- `LOGSEQ_API_TOKEN`: Your LogSeq API token
- `LOGSEQ_API_URL`: LogSeq server URL (default: `http://localhost:12315`)

### Installation Verification

#### Test LogSeq API connectivity
```bash
python -c "
from mcp_logseq.logseq import LogSeq
api = LogSeq(api_key='your_token')
result = api.list_pages()
print(f'Connected! Found {len(result)} pages')
"
```

#### Verify MCP server registration
```bash
# For Claude Code
claude mcp list

# Should show mcp-logseq in the list
```

#### Test with MCP Inspector (for debugging)
```bash
npx @modelcontextprotocol/inspector mcp-logseq
```

## Tools

The server implements 6 tools to interact with LogSeq:

- **create_page**: Create a new page with content
- **list_pages**: List all pages in the current graph (with journal filtering)
- **get_page_content**: Retrieve content of a specific page (text or JSON format)
- **delete_page**: Remove a page from the graph
- **update_page**: Update existing page content and/or properties
- **search**: Search for content across pages, blocks, and files

### Example prompts

It's good to first instruct Claude to use LogSeq. Then it will always call the tool.

Example prompts:
- Get the contents of my latest meeting notes and summarize them
- Search for all pages where Project X is mentioned and explain the context
- Create a new page with today's meeting notes
- Update the project status page with the latest updates

## Configuration

### Environment Variables

- **LOGSEQ_API_TOKEN** (required): Bearer token from LogSeq API control panel → Authorization tokens
- **LOGSEQ_API_URL** (optional): LogSeq server URL (default: `http://localhost:12315`)

### Alternative Configuration Methods

#### Using .env file
Create a `.env` file in the project directory:
```
LOGSEQ_API_TOKEN=your_token_here
LOGSEQ_API_URL=http://localhost:12315
```

#### Using system environment variables
```bash
export LOGSEQ_API_TOKEN=your_token_here
export LOGSEQ_API_URL=http://localhost:12315
```

## Troubleshooting

### Common Issues

#### "LOGSEQ_API_TOKEN environment variable required"
- Ensure LogSeq HTTP API is enabled in Settings → Features
- Start the API server using the API button (🔌) in LogSeq's main interface
- Generate and copy the API token from "Authorization tokens" in the API control panel
- Verify token is correctly set in your configuration

#### Connection errors to LogSeq
- Confirm LogSeq is running
- Check that HTTP API server is enabled in Settings → Features
- **Important**: Make sure the API server is actually started (click "Start server" in the API control panel)
- Verify the server is running on port 12315
- Test connectivity with the verification command above

#### MCP server not found in Claude Code
- Run `claude mcp list` to check if server is registered
- Verify the command and arguments in your configuration
- Check that `uv` and Python dependencies are properly installed

#### Empty or missing page content
- Some LogSeq versions may not support all API methods
- Check LogSeq logs for API errors
- Verify page names match exactly (case-sensitive)

## Development

For local development, testing, and contributing to this project, see [DEVELOPMENT.md](DEVELOPMENT.md).
