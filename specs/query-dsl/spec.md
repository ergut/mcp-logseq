# Feature Specification: Query DSL (Search by Properties)

**Feature Branch**: `query-dsl`
**Input**: User description: "@FEATURE_QUERY_DSL.md"

## Context and Understanding

Logseq has a powerful DSL (Domain Specific Language) query system that allows searching pages and blocks by properties, tags, and logical combinations. Currently, the MCP server does not expose this capability, making it impossible to perform searches like:

- "All pages with `status:: active`"
- "All customers (`type:: customer`) that are active"
- "Blocks marked as TODO created this week"

**Current Limitations:**

| Tool | Can search by property? |
|------|------------------------|
| `list_pages` | ❌ Lists everything, no filter |
| `search` | ❌ Full-text search only |
| `get_page_content` | ❌ Shows one page, doesn't search |

To find pages by property today, one would need to list all pages and call `get_page_content` on each one — completely impractical.

## Feature Description

This feature adds two complementary MCP tools that expose Logseq's DSL query capabilities:

1. **`query`** - A generic DSL query tool for maximum flexibility, allowing advanced users to execute any valid Logseq query
2. **`find_pages_by_property`** - A simplified interface for the most common use case: finding pages by a specific property and optional value

These tools unlock powerful metadata-based searching that was previously unavailable through the MCP interface.

## Requirements

### Proposed Solution

- **US-001**: As an MCP user, I want to execute arbitrary Logseq DSL queries so that I can search for pages and blocks using complex criteria
- **US-002**: As an MCP user, I want a simple way to find pages by property name and value so that I don't need to learn DSL syntax for common searches
- **US-003**: As an MCP user, I want query results formatted in a readable way so that I can easily understand what was found
- **US-004**: As a developer, I want unit tests for both new tools so that the feature is maintainable
- **US-005**: As a developer, I want the tools registered in the MCP server so that they are available to clients

### Functional Requirements

- **FR-001**: System MUST provide a `query` tool that accepts a DSL query string and returns matching results
- **FR-002**: System MUST provide a `find_pages_by_property` tool that accepts a property name and optional value
- **FR-003**: System MUST use the `logseq.DB.q` API method to execute DSL queries
- **FR-004**: System MUST format query results showing page/block names and relevant properties
- **FR-005**: System MUST handle empty results gracefully with informative messages
- **FR-006**: System MUST handle invalid queries with clear error messages and documentation reference
- **FR-007**: The `find_pages_by_property` tool MUST support searching with just a property name (returns all pages with that property)
- **FR-008**: The `find_pages_by_property` tool MUST support searching with property name AND value (returns pages matching both)
- **FR-009**: System MUST properly escape special characters in property values when building queries
- **FR-010**: Both tools MUST support an optional `limit` parameter (default: 100) to control result set size
- **FR-011**: The `query` tool MUST support an optional `result_type` parameter to filter results (pages_only, blocks_only, all - default: all)
- **FR-012**: Query results MUST include a type indicator for each item (page or block) in a unified list format

### DSL Query Syntax Support

The `query` tool should support standard Logseq DSL syntax including:

```clojure
;; Page property queries
(page-property <name> <value>)
(page-property <name>)           ;; any value

;; Block property queries
(property <name> <value>)

;; Logical combinations
(and <query1> <query2> ...)
(or <query1> <query2> ...)
(not <query>)

;; Tasks/TODOs
(task todo)
(task now later done)

;; Tags
(page-tags [[tag-name]])

;; References
(page [[Page Name]])

;; Date ranges (for journals)
(between [[Dec 1st, 2024]] [[Dec 15th, 2024]])
```

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can find pages by property in a single MCP tool call instead of multiple calls
- **SC-002**: The `query` tool successfully executes valid Logseq DSL queries and returns results
- **SC-003**: The `find_pages_by_property` tool returns correct results for property searches
- **SC-004**: All new unit tests pass
- **SC-005**: Integration test confirms 12 tools are registered (current 10 + 2 new)
- **SC-006**: Error messages for invalid queries include helpful guidance

## Clarification Needed

*All clarifications resolved.*

### Decisions Made

1. **Result Pagination**: ✅ **Option A** - Add optional `limit` parameter (default: 100) to both tools

2. **Block vs Page Results**: ✅ **Options B + C** - Unified list with type indicator per item, plus optional `result_type` parameter to filter (pages_only, blocks_only, all)

## Notes

### API Reference
- **Logseq API Method**: `logseq.DB.q` - Run a DSL query
- **Documentation**: https://docs.logseq.com/#/page/queries
- **Plugin API Reference**: https://logseq.github.io/plugins/interfaces/IDBProxy.html

### Example Queries

```clojure
;; All active customers
(and (page-property type customer) (page-property status active))

;; High priority project pages
(and (page-property type project) (page-property priority high))

;; Incomplete TODOs
(task todo now later)

;; Pages modified in December
(between [[Dec 1st, 2024]] [[Dec 31st, 2024]])
```

### Implementation Notes
- The feature file includes sample implementation code that follows existing patterns in the codebase
- Both tools use the same underlying `query_dsl` API method - `find_pages_by_property` is a convenience wrapper
- Property values containing quotes need proper escaping
