# Architecture: Query DSL (Search by Properties)

**Feature**: Query DSL
**Date**: 2025-12-16
**Branch**: `query-dsl`
**Specs**: [spec.md](./spec.md)

## Summary

This feature adds two new MCP tools (`query` and `find_pages_by_property`) that expose Logseq's DSL query capabilities. The implementation follows the established tool handler pattern: adding API methods to `logseq.py`, creating tool handler classes in `tools.py`, and registering them in `server.py`.

## Technical Context

**Language/Stack**: Python 3.11+
**Key Dependencies**: requests, mcp (existing)
**Storage**: N/A (queries Logseq API directly)
**Testing**: pytest with unittest.mock and responses library
**Platform**: MCP server (stdio)

## Technical Decisions

### Decision 1: Single `query_dsl` API Method

**What**: Both tools will use a single underlying `query_dsl()` method in the API client
**Why**: The `find_pages_by_property` tool is essentially a convenience wrapper that constructs a DSL query string - no need for separate API methods
**Alternatives Considered**: Separate API methods for each tool - rejected as it would duplicate logic
**Trade-offs**: Slightly more string construction in the convenience method, but cleaner API surface

### Decision 2: Result Type Detection via Heuristics

**What**: Detect whether a result item is a page or block based on available fields (`originalName`/`name` = page, `content`/`block/content` = block)
**Why**: Logseq's `DB.q` returns mixed results - the response structure varies by query type
**Alternatives Considered**:
- Always return raw JSON - rejected as it's not user-friendly
- Separate API calls - rejected as Logseq doesn't provide type-specific query endpoints
**Trade-offs**: Heuristics may occasionally misclassify edge cases, but covers 99% of use cases

### Decision 3: Client-Side Filtering for result_type

**What**: Apply `result_type` filter (pages_only, blocks_only, all) after receiving results from Logseq
**Why**: Logseq's DSL doesn't have a built-in type filter - filtering must be done post-query
**Alternatives Considered**: Modify DSL query to only match certain types - rejected as DSL syntax varies by query type
**Trade-offs**: May fetch more data than needed, but simplifies implementation and maintains query flexibility

### Decision 4: Default Limit of 100

**What**: Both tools default to returning max 100 results
**Why**: Balances usability (enough results for most queries) with performance (prevents overwhelming output)
**Alternatives Considered**: No limit (rejected - could return thousands), lower limit like 20 (rejected - too restrictive for property searches)
**Trade-offs**: Users may need to increase limit for exhaustive searches

## Architecture Overview

The current MCP server has 6 tools. This feature adds 2 more tools that query Logseq's database using DSL syntax.

### Component Structure

**New Files/Modules:**
```
None - all changes go into existing files
```

**Modified Files:**
```
src/mcp_logseq/logseq.py      - Add query_dsl() method
src/mcp_logseq/tools.py       - Add QueryToolHandler and FindPagesByPropertyToolHandler classes
src/mcp_logseq/server.py      - Register new tool handlers
tests/conftest.py             - Add mock responses for query results
tests/unit/test_tool_handlers.py - Add test classes for new handlers
tests/unit/test_logseq_api.py    - Add API method tests
tests/integration/test_mcp_server.py - Update tool count to 8
```

### Component Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Client                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     server.py                                    │
│  - Registers QueryToolHandler                                    │
│  - Registers FindPagesByPropertyToolHandler                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      tools.py                                    │
│  ┌─────────────────────────┐  ┌──────────────────────────────┐  │
│  │   QueryToolHandler      │  │ FindPagesByPropertyToolHandler│  │
│  │   - query (required)    │  │ - property_name (required)    │  │
│  │   - limit (optional)    │  │ - property_value (optional)   │  │
│  │   - result_type (opt)   │  │ - limit (optional)            │  │
│  └───────────┬─────────────┘  └──────────────┬───────────────┘  │
│              │                               │                   │
│              └───────────────┬───────────────┘                   │
│                              ▼                                   │
│                    Formats results with                          │
│                    type indicators                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      logseq.py                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    query_dsl(query: str)                     ││
│  │                                                              ││
│  │  POST /api                                                   ││
│  │  {"method": "logseq.DB.q", "args": [query]}                 ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Logseq HTTP API                             │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

**Query Tool Flow:**
1. MCP client calls `query` tool with DSL string
2. QueryToolHandler validates args and calls `api.query_dsl(query)`
3. LogSeq client POSTs to `/api` with `logseq.DB.q` method
4. Results returned, filtered by `result_type` if specified
5. Results limited to `limit` count
6. Each result annotated with type indicator (📄 page / 📝 block)
7. Formatted text response returned to client

**Find Pages By Property Flow:**
1. MCP client calls `find_pages_by_property` with property_name and optional value
2. FindPagesByPropertyToolHandler constructs DSL query:
   - With value: `(page-property {name} "{value}")`
   - Without value: `(page-property {name})`
3. Calls `api.query_dsl(constructed_query)`
4. Results limited to `limit` count
5. Formatted text response with property values shown

## Implementation Approach

### User Story Mapping

**US-001 (P1): Execute arbitrary DSL queries**
- Files: `logseq.py`, `tools.py`, `server.py`
- Key components: `query_dsl()` method, `QueryToolHandler` class
- Testing: Mock API responses, test various query types

**US-002 (P1): Simple property search**
- Files: `tools.py`
- Key components: `FindPagesByPropertyToolHandler` class
- Dependencies: Uses `query_dsl()` from US-001
- Testing: Test with/without property value, escaping

**US-003 (P1): Readable result formatting**
- Files: `tools.py`
- Key components: Result formatting in both handlers
- Testing: Verify output format, type indicators

**US-004 (P2): Unit tests**
- Files: `tests/unit/test_tool_handlers.py`, `tests/unit/test_logseq_api.py`, `tests/conftest.py`
- Testing: Tool description validation, success/error cases

**US-005 (P2): Register tools**
- Files: `server.py`, `tests/integration/test_mcp_server.py`
- Testing: Integration test verifies 8 tools registered

### File Structure

```
mcp-logseq/
├── src/mcp_logseq/
│   ├── logseq.py              # MODIFIED: Add query_dsl()
│   ├── tools.py               # MODIFIED: Add 2 new handler classes
│   └── server.py              # MODIFIED: Register 2 new handlers
├── tests/
│   ├── conftest.py            # MODIFIED: Add query mock responses
│   ├── unit/
│   │   ├── test_logseq_api.py      # MODIFIED: Add query API tests
│   │   └── test_tool_handlers.py   # MODIFIED: Add handler tests
│   └── integration/
│       └── test_mcp_server.py      # MODIFIED: Update tool count to 8
└── specs/query-dsl/
    ├── spec.md
    └── architecture.md         # THIS FILE
```

## Integration Points

- **Integration with existing tools**: None - these are standalone query tools
- **New APIs/Interfaces**: Two new MCP tools exposed via `list_tools` and `call_tool`
- **Dependencies**: Relies on existing `LogSeq` client infrastructure

## Technical Constraints

- Must maintain backward compatibility with existing 6 tools
- Query syntax is determined by Logseq - we pass through DSL strings directly
- Result structure varies by query type - formatting must handle multiple shapes

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Invalid DSL query crashes server | Medium | Catch exceptions, return user-friendly error with doc link |
| Large result sets cause timeouts | Low | Default limit of 100, configurable by user |
| Logseq API changes query response format | Low | Type detection uses multiple field checks as fallback |
| Property values with special chars break query | Medium | Escape quotes in property values |

## Open Questions

None - all technical decisions resolved.

## Next Steps

1. Review this architecture
2. Run `/plan` to generate implementation tasks
