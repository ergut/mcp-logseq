# Tasks: Query DSL (Search by Properties)

**Branch**: `query-dsl`
**Specs**: [spec.md](./spec.md)
**Architecture**: [architecture.md](./architecture.md)
**Status**: ✅ Complete

---

## Phase 1: Implementation - API Client Method (~30min)

**Purpose**: Add the core DSL query method to the LogSeq API client

- [x] T001 Add `query_dsl()` method to `src/mcp_logseq/logseq.py`

**Checkpoint**: ✅ API method implemented, ready for tool handlers

**Notes:**
- Uses `logseq.DB.q` API method
- Returns raw query results from Logseq
- Follows existing method patterns (logging, error handling, try/except)

---

## Phase 2: Implementation - Tool Handlers (~1h)

**Purpose**: Create the MCP tool handler classes with result formatting

- [x] T002 Add `QueryToolHandler` class to `src/mcp_logseq/tools.py`
  - Parameters: `query` (required), `limit` (optional, default 100), `result_type` (optional: pages_only, blocks_only, all)
  - Implemented type detection heuristics (page vs block)
  - Formats results with type indicators (📄 page / 📝 block)
  - Handles errors with helpful messages and doc link

- [x] T003 Add `FindPagesByPropertyToolHandler` class to `src/mcp_logseq/tools.py`
  - Parameters: `property_name` (required), `property_value` (optional), `limit` (optional, default 100)
  - Constructs DSL query: `(page-property name)` or `(page-property name "value")`
  - Escapes special characters in property values
  - Formats results showing property values

- [x] T004 Register both handlers in `src/mcp_logseq/server.py`

**Checkpoint**: ✅ Tools registered and available via MCP protocol

**Notes:**
- Followed existing handler patterns (SearchToolHandler as reference)
- `find_pages_by_property` uses `query_dsl()` internally
- Error handling includes link to Logseq query docs

---

## Phase 3: Testing (~45min)

**Purpose**: Add comprehensive unit tests for new functionality

- [x] T005 Add mock responses for query results to `tests/conftest.py`
  - `query_dsl_pages_success`: List of page results
  - `query_dsl_blocks_success`: List of block results
  - `query_dsl_mixed_success`: Mixed pages and blocks
  - `query_dsl_empty`: Empty results

- [x] T006 [P] Add `TestQueryToolHandler` class to `tests/unit/test_tool_handlers.py`
  - 8 test cases covering: description, success, empty, limit, pages_only, blocks_only, invalid query, missing args

- [x] T007 [P] Add `TestFindPagesByPropertyToolHandler` class to `tests/unit/test_tool_handlers.py`
  - 7 test cases covering: description, with value, without value, empty, limit, escaping quotes, missing args

- [x] T008 [P] Add query API tests to `tests/unit/test_logseq_api.py`
  - `test_query_dsl_success`
  - `test_query_dsl_empty_results`
  - `test_query_dsl_network_error`

- [x] T009 Update `tool_handlers` fixture in `tests/conftest.py` to include new handlers

- [x] T010 Update integration test tool count to 8 in `tests/integration/test_mcp_server.py`

**Checkpoint**: ✅ All tests pass with `uv run pytest`

**Notes:**
- Added 18 new tests (68 total now)
- All tests follow existing patterns

---

## Phase 4: Validation (~15min)

**Purpose**: Final validation

- [x] T011 Run full test suite: `LOGSEQ_API_TOKEN=test_token uv run pytest -v`
- [x] T012 Verify 8 tools appear in server (via integration test)
- [ ] T013 Test with real LogSeq instance (optional)

**Checkpoint**: ✅ Feature complete and validated

**Notes:**
- All 68 tests pass
- Total tools: 8

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: API Client Method
    ↓
Phase 2: Tool Handlers (depends on Phase 1)
    ↓
Phase 3: Testing (depends on Phase 1 & 2)
    ↓
Phase 4: Validation (depends on all phases)
```

### Parallel Opportunities

**Within Phase 3:**
- T006, T007, T008 are marked [P] - different test classes can be written in parallel
- T005 must complete first (fixtures needed by tests)

---

## Implementation Strategy

### Recommended Approach

1. Complete Phase 1 (API method) - ~30 min ✅
2. Complete Phase 2 (Tool handlers) - ~1 hour ✅
3. Complete Phase 3 (Tests) - ~45 min ✅
4. Complete Phase 4 (Validation) - ~15 min ✅

**Total estimated time: ~2.5 hours**

### Single-Session Execution

This feature was completed in a single session following the established patterns in the codebase.

---

## Progress Tracking

**Emoji Legend:**
- ⏳ Not Started
- ⏰ In Progress
- ✅ Completed

---

## Notes

**Key Implementation References:**
- Feature requirements: `FEATURE_QUERY_DSL.md` (includes sample code)
- Existing patterns: `SearchToolHandler` in `tools.py`
- API patterns: `search_content()` in `logseq.py`
- Test patterns: `TestSearchToolHandler` in `test_tool_handlers.py`

**Logseq API Method:**
- `logseq.DB.q` - Run a DSL query
- Returns array of matching pages/blocks

**Result Type Detection:**
- Page: has `originalName` or `name` field, without `content` field
- Block: has `content` or `block/content` field

**Output Format Examples:**

Query tool:
```
# Query Results

**Query:** `(page-property type customer)`

1. 📄 **Customer/Orienteme** (type: customer, status: active)
2. 📄 **Customer/InsideOut** (type: customer)
3. 📝 Block content here...

---
**Total: 3 results**
```

Find pages by property:
```
# Pages with 'type = customer'

- **Customer/Orienteme** (type: customer)
- **Customer/InsideOut** (type: customer)

---
**Total: 2 pages**
```
