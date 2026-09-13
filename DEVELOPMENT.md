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

# Install development dependencies (including vector extras required for tests)
uv sync --dev --extra vector
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
- **680+ tests** with 100% success rate (see TESTING.md for current counts)

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

The CLI entrypoint logs to stderr at `INFO` by default. There is no default log file.

- `LOGSEQ_LOG_LEVEL` sets the level (e.g. `DEBUG`); an invalid value falls back to `INFO`.
- `LOGSEQ_LOG_FILE` (opt-in) additionally writes the same log to the given file. If the file cannot be opened, logging continues to stderr only.

```bash
# Verbose logging to stderr plus a file
LOGSEQ_LOG_LEVEL=DEBUG LOGSEQ_LOG_FILE=/tmp/mcp-logseq.log \
  uv run --directory /path/to/mcp-logseq mcp-logseq
```

## Project Structure

```
mcp-logseq/
├── src/mcp_logseq/
│   ├── __init__.py          # CLI entry point (argument parsing, logging setup)
│   ├── server.py            # MCP server initialization and tool registration
│   ├── logseq.py            # LogSeq API client
│   ├── settings.py          # Runtime settings (env vars / config file)
│   ├── config.py            # Config file loading (incl. vector config)
│   ├── access.py            # Access control: exclude tags, namespaces, access policies
│   ├── namespace.py         # Namespace matching helpers
│   ├── parser.py            # Markdown block parsing
│   ├── tools/               # MCP tool handlers
│   │   ├── base.py          # ToolHandler base class, API factory
│   │   ├── pages.py         # Page tools
│   │   ├── blocks.py        # Block tools
│   │   ├── namespace.py     # Namespace tools
│   │   └── search.py        # search / query tools
│   ├── vector/              # Optional vector search (chunker, db, embedder, index, state, sync, types)
│   ├── transport/           # HTTP transport and auth
│   └── bin/
│       └── logseq_sync.py   # logseq-sync CLI entrypoint
├── tests/
│   ├── unit/                # Unit tests (tests/unit/vector/ for vector search)
│   └── integration/         # Integration tests
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
- **`tools/`**: Tool handlers that transform API responses for Claude (`pages.py`, `blocks.py`, `namespace.py`, `search.py`; base class in `base.py`)
- **`access.py`**: Access control lists and the declarative `AccessPolicy` classes handlers attach to
- **`vector/`**: Optional vector search tools, registered only when enabled in the config file

### Tool Handler Pattern

Each LogSeq operation is implemented as a `ToolHandler` subclass:

```python
class ExampleToolHandler(ToolHandler):
    access_policy = [access.NamespaceName("page_name")]

    def __init__(self):
        super().__init__("example_tool")

    def get_tool_description(self) -> Tool:
        # Define tool schema

    def _run(self, api, args: dict) -> list[TextContent]:
        # Implement tool logic; `api` is the LogSeq client
```

The base `ToolHandler.run_tool` builds the API client, runs every policy in `access_policy` (raising `AccessDenied` on a restricted page or block), then calls `_run`. Handlers never wire access checks by hand.

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

1. Create a new `ToolHandler` subclass in the matching module under `src/mcp_logseq/tools/` (`pages.py`, `blocks.py`, `namespace.py`, `search.py`) and export it from `tools/__init__.py`
2. Implement `__init__` (tool name), `get_tool_description` and `_run`
3. Declare `access_policy`: a list of `access.AccessPolicy` objects (`NamespaceName`, `PageTag`, `BlockNamespace`, `BlockTag`), each naming the argument that carries the page name or block UUID. Use `[]` only if the tool needs no pre-dispatch gate or filters results itself via `access.is_page_blocked`
4. Register it in `_register_all_tool_handlers` in `server.py`; if it writes to the graph, also add its name to `_WRITE_TOOL_NAMES` so `--read-only` skips it
5. Add the handler to `EXPECTED_POLICIES` in `tests/unit/test_access_policy_coverage.py` (the test fails otherwise)
6. Add corresponding LogSeq API method if needed
7. Write unit and integration tests
8. Update documentation

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