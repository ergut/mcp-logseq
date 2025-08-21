# Testing Framework Documentation

This document provides comprehensive information about the testing framework for the MCP LogSeq server project.

## Overview

The testing framework is built using pytest and provides comprehensive coverage for all components of the MCP LogSeq server. It includes unit tests, integration tests, and shared fixtures to ensure code quality and reliability.

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── unit/                      # Unit tests for individual components
│   ├── test_logseq_api.py     # Tests for LogSeq API client
│   └── test_tool_handlers.py  # Tests for MCP tool handlers
└── integration/               # Integration tests for system components
    └── test_mcp_server.py     # Tests for MCP server integration
```

## Dependencies

The testing framework uses the following dependencies:

- **pytest** - Main testing framework
- **pytest-mock** - Mocking utilities for pytest
- **responses** - HTTP request mocking library
- **pytest-asyncio** - Async testing support

## Running Tests

### Basic Usage

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with short traceback format
uv run pytest --tb=short
```

### Running Specific Test Categories

```bash
# Run only unit tests
uv run pytest tests/unit/

# Run only integration tests
uv run pytest tests/integration/

# Run specific test file
uv run pytest tests/unit/test_logseq_api.py

# Run specific test class
uv run pytest tests/unit/test_logseq_api.py::TestLogSeqAPI

# Run specific test method
uv run pytest tests/unit/test_logseq_api.py::TestLogSeqAPI::test_create_page_success
```

### Test Output Options

```bash
# Show detailed output for failed tests
uv run pytest -v --tb=long

# Show only test names and results
uv run pytest -q

# Stop after first failure
uv run pytest -x

# Show local variables in tracebacks
uv run pytest -l
```

## Test Coverage

### Unit Tests

#### LogSeq API Client (`test_logseq_api.py`)

Tests for the `LogSeq` class covering:

- **Initialization**: Default and custom parameters
- **URL Generation**: Base URL construction
- **Authentication**: Header generation
- **Page Operations**: Create, read, update, delete
- **Search Functionality**: Content search with options
- **Error Handling**: Network errors, API failures
- **Edge Cases**: Non-existent pages, empty responses

**Key Test Methods:**
- `test_create_page_success()` - Successful page creation
- `test_get_page_content_success()` - Page content retrieval
- `test_delete_page_not_found()` - Error handling for missing pages
- `test_search_content_with_options()` - Search with custom parameters

#### Tool Handlers (`test_tool_handlers.py`)

Tests for all MCP tool handler classes:

- **Schema Validation**: Tool description and input schema
- **Successful Operations**: Normal execution paths
- **Error Scenarios**: Missing arguments, API failures
- **Input Validation**: Required parameters, type checking
- **Output Formatting**: Text and JSON response formats

**Covered Tool Handlers:**
- `CreatePageToolHandler`
- `ListPagesToolHandler`
- `GetPageContentToolHandler`
- `DeletePageToolHandler`
- `UpdatePageToolHandler`
- `SearchToolHandler`

### Integration Tests

#### MCP Server Integration (`test_mcp_server.py`)

Tests for the complete MCP server system:

- **Tool Registration**: Handler registration and discovery
- **Tool Interface**: Schema compliance and method availability
- **End-to-End Execution**: Complete tool execution flows
- **Error Propagation**: Exception handling across layers
- **Custom Handlers**: Dynamic tool handler addition

**Key Integration Areas:**
- Handler registration system
- Tool discovery and validation
- Cross-component communication
- Error handling consistency

## Test Fixtures and Mocking

### Shared Fixtures (`conftest.py`)

The testing framework provides several shared fixtures:

#### Core Fixtures

- `mock_api_key` - Provides a test API key
- `logseq_client` - Pre-configured LogSeq client instance
- `tool_handlers` - Dictionary of all tool handler instances
- `mock_env_api_key` - Mocked environment variable

#### Mock Data Fixtures

- `mock_logseq_responses` - Comprehensive mock API responses including:
  - Successful page creation
  - Page listing with journal filtering
  - Page content with metadata and blocks
  - Search results with various content types
  - Error scenarios and edge cases

### HTTP Mocking Strategy

The framework uses the `responses` library to mock HTTP requests:

```python
@responses.activate
def test_api_call(self, logseq_client):
    responses.add(
        responses.POST,
        "http://127.0.0.1:12315/api",
        json={"success": True},
        status=200
    )
    # Test implementation
```

### Environment Mocking

Environment variables are mocked using `patch.dict`:

```python
@patch.dict('os.environ', {'LOGSEQ_API_TOKEN': 'test_token'})
def test_with_env_var(self):
    # Test implementation
```

## Writing New Tests

### Test Organization

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Use descriptive test class and method names
- Group related tests in the same class

### Test Naming Conventions

```python
class TestComponentName:
    def test_method_name_success(self):
        """Test successful operation."""
        
    def test_method_name_failure_scenario(self):
        """Test specific failure case."""
        
    def test_method_name_edge_case(self):
        """Test edge case handling."""
```

### Best Practices

1. **Isolation**: Each test should be independent
2. **Mocking**: Mock external dependencies (HTTP calls, file system)
3. **Assertions**: Use specific, meaningful assertions
4. **Documentation**: Include clear docstrings
5. **Coverage**: Test both success and failure paths

### Adding New Fixtures

Add new fixtures to `conftest.py`:

```python
@pytest.fixture
def new_fixture():
    """Description of what this fixture provides."""
    return fixture_data
```

## Continuous Integration

The testing framework is designed to work well in CI environments:

- All tests are isolated and don't require external services
- HTTP requests are mocked to avoid network dependencies
- Tests run quickly (< 1 second for full suite)
- Clear error messages for debugging failures

## Debugging Tests

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed with `uv sync --dev`
2. **Mock Failures**: Verify mock setup matches actual API calls
3. **Async Issues**: Use `pytest.mark.asyncio` for async tests

### Debugging Commands

```bash
# Run with Python debugger on failure
uv run pytest --pdb

# Show local variables in tracebacks
uv run pytest -l

# Increase verbosity for debugging
uv run pytest -vvv
```

### Test-Specific Debugging

```python
def test_debug_example(self):
    import pdb; pdb.set_trace()  # Breakpoint
    # Test code here
```

## Performance Considerations

- **Fast Execution**: Full test suite runs in < 1 second
- **Parallel Execution**: Tests can run in parallel (use `pytest-xdist`)
- **Resource Usage**: Minimal memory footprint with proper mocking

## Maintenance

### Updating Tests

When modifying the codebase:

1. Update corresponding tests
2. Add tests for new functionality
3. Ensure all tests pass before committing
4. Update mock data if API responses change

### Test Dependencies

Keep test dependencies up to date:

```bash
# Update development dependencies
uv sync --dev --upgrade
```

## Test Statistics

Current test coverage:

- **Total Tests**: 50
- **Unit Tests**: 35
- **Integration Tests**: 15
- **Success Rate**: 100%
- **Execution Time**: ~0.3 seconds