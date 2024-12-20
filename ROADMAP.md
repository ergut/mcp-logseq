# LogSeq MCP Server Roadmap

## Implemented Features

### Core Functionality
- ✅ LogSeq API client setup with proper error handling and logging
- ✅ Environment variable configuration for API token
- ✅ Basic project structure and package setup

### Tools
- ✅ Create Page (`create_page`)
  - Create new pages with content
  - Support for basic markdown content
- ✅ List Pages (`list_pages`)
  - List all pages in the graph
  - Filter journal/daily notes
  - Display page metadata (tags, properties)
  - Alphabetical sorting

## Planned Features

### High Priority
- 🔲 Get Page Content (`get_page_content`)
  - Retrieve content of a specific page
  - Support for JSON metadata format
- 🔲 Search functionality (`search`)
  - Full-text search across pages
  - Support for tags and properties filtering
- 🔲 Delete Page (`delete_page`)
  - Remove pages from the graph
  - Safety checks before deletion

### Medium Priority
- 🔲 Update Page Content (`update_page`)
  - Modify existing page content
  - Support for partial updates
- 🔲 Page Properties Management
  - Add/update page properties
  - Manage page tags
- 🔲 Block Level Operations
  - Create/update/delete blocks
  - Move blocks between pages

### Low Priority
- 🔲 Graph Management
  - List available graphs
  - Switch between graphs
- 🔲 Journal Pages Management
  - Create/update daily notes
  - Special handling for journal pages
- 🔲 Page Templates
  - Create pages from templates
  - Manage template library

## Technical Improvements
- 🔲 Better error handling for API responses
- 🔲 Comprehensive logging for debugging
- 🔲 Unit tests for core functionality
- 🔲 Integration tests with LogSeq
- 🔲 Documentation
  - API documentation
  - Usage examples
  - Configuration guide

## Notes
- Priority levels may change based on user feedback
- Some features depend on LogSeq Local REST API capabilities
- Features might be adjusted as LogSeq's API evolves
