# Development Guide

This guide covers local development, testing, and contributing to the MCP LogSeq server.

## Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) for Python package management
- LogSeq with HTTP API enabled
- Git

## Local Development Setup

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/ergut/mcp-logseq.git
cd mcp-logseq

# Install dependencies
uv sync

# Install development dependencies
uv sync --dev
```

### 2. Environment Configuration

Create a `.env` file in the project root:

```bash
LOGSEQ_API_TOKEN=your_token_here
LOGSEQ_API_URL=http://localhost:12315
```

### 3. Local Installation for Testing

#### For Claude Code (Development)
```bash
# Add to Claude Code with local development setup
claude mcp add mcp-logseq-dev \
  --env LOGSEQ_API_TOKEN=your_token_here \
  --env LOGSEQ_API_URL=http://localhost:12315 \
  -- uv run --directory /path/to/mcp-logseq mcp-logseq
```

#### For Claude Desktop (Development)
```json
{
  "mcpServers": {
    "mcp-logseq-dev": {
      "command": "uv",
      "args": [
        "run", 
        "--directory", 
        "/path/to/mcp-logseq",
        "mcp-logseq"
      ],
      "env": {
        "LOGSEQ_API_TOKEN": "your_token_here",
        "LOGSEQ_API_URL": "http://localhost:12315"
      }
    }
  }
}
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run specific test categories
uv run pytest tests/unit/       # Unit tests only
uv run pytest tests/integration/ # Integration tests only

# Run with coverage
uv run pytest --cov=mcp_logseq --cov-report=html
```

### Test Structure

- **Unit tests**: Test individual components (LogSeq API client, tool handlers)
- **Integration tests**: Test MCP server functionality end-to-end
- **HTTP mocking**: Uses `responses` library for reliable testing
- **50+ comprehensive tests** with 100% success rate

For detailed testing documentation, see [TESTING.md](TESTING.md).

## Debugging

### MCP Inspector

The best way to debug MCP servers is using the MCP Inspector:

```bash
# Debug local development version
npx @modelcontextprotocol/inspector \
  uv run --directory /path/to/mcp-logseq mcp-logseq
```

### Direct Testing

Test the LogSeq API connection directly:

```bash
# Test API connectivity
uv run python -c "
from mcp_logseq.logseq import LogSeq
api = LogSeq(api_key='your_token')
result = api.list_pages()
print(f'Connected! Found {len(result)} pages')
"

# Test specific API endpoints
uv run python -c "
from mcp_logseq.logseq import LogSeq
api = LogSeq(api_key='your_token')
print('Testing create_page...')
api.create_page('Test Page', 'Test content')
print('Success!')
"
```

### Logging

The server uses comprehensive logging. Check the log file:

```bash
# Log file is now stored in user cache directory
tail -f ~/.cache/mcp-logseq/mcp_logseq.log
```

## Project Structure

```
mcp-logseq/
├── src/mcp_logseq/
│   ├── __init__.py          # Package entry point
│   ├── server.py            # MCP server initialization
│   ├── logseq.py           # LogSeq API client
│   └── tools.py            # MCP tool handlers
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── README.md               # User documentation
├── DEVELOPMENT.md          # This file
├── ROADMAP.md             # Project roadmap
├── pyproject.toml         # Package configuration
└── .env.example           # Environment template
```

## Architecture

### Core Components

- **`server.py`**: MCP server setup, tool registration, request handling
- **`logseq.py`**: LogSeq API client with JSON-RPC methods
- **`tools.py`**: Tool handlers that transform API responses for Claude

### Tool Handler Pattern

Each LogSeq operation is implemented as a `ToolHandler` subclass:

```python
class ExampleToolHandler(ToolHandler):
    def get_tool_description(self) -> Tool:
        # Define tool schema
        
    def run_tool(self, args: dict) -> list[TextContent]:
        # Implement tool logic
```

## Contributing

### Before Submitting

1. **Run tests**: Ensure all tests pass
2. **Check typing**: Run `uv run pyright`
3. **Test locally**: Verify with both Claude Code and Claude Desktop
4. **Update docs**: Update README.md or DEVELOPMENT.md if needed

### Code Style

- Follow existing patterns in the codebase
- Use type hints for all functions
- Add comprehensive error handling
- Include logging for debugging

### Adding New Tools

1. Create a new `ToolHandler` subclass in `tools.py`
2. Implement required methods
3. Register the tool in `server.py`
4. Add corresponding LogSeq API method if needed
5. Write unit and integration tests
6. Update documentation

## Building and Distribution

### Prepare for Release

```bash
# Sync dependencies
uv sync

# Run all tests
uv run pytest

# Check package can be built
uv build
```

### Publishing to PyPI

```bash
# Build the package
uv build

# Publish (requires credentials)
uv publish
```

## Troubleshooting Development Issues

### Common Problems

1. **Import errors**: Make sure you're in the project directory and dependencies are installed
2. **API connection failures**: Verify LogSeq is running and API server is started
3. **Token issues**: Check that your `.env` file has the correct token
4. **MCP client issues**: Restart Claude Code/Desktop after configuration changes

### Getting Help

- Check existing issues: https://github.com/ergut/mcp-logseq/issues
- Review LogSeq API documentation
- Use MCP Inspector for debugging
- Check Claude Code/Desktop documentation for MCP setup