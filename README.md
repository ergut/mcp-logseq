# MCP server for LogSeq

MCP server to interact with LogSeq via its API.

## Components

### Tools

The server implements multiple tools to interact with LogSeq:

- list_graphs: Lists all available graphs
- list_pages: Lists all pages in the current graph
- get_page_content: Return the content of a single page
- search: Search for content across all pages
- create_page: Create a new page
- update_page: Update content of an existing page
- delete_page: Delete a page

### Example prompts

It's good to first instruct Claude to use LogSeq. Then it will always call the tool.

Example prompts:
- Get the contents of my latest meeting notes and summarize them
- Search for all pages where Project X is mentioned and explain the context
- Create a new page with today's meeting notes
- Update the project status page with the latest updates

## Configuration

### LogSeq API Configuration

You can configure the environment with LogSeq API settings in two ways:

1. Add to server config (preferred)

```json
{
  "mcp-logseq": {
    "command": "uvx",
    "args": [
      "mcp-logseq"
    ],
    "env": {
      "LOGSEQ_API_TOKEN": "<your_api_token_here>",
      "LOGSEQ_API_URL": "http://localhost:12315"
    }
  }
}
```

2. Create a `.env` file in the working directory with the required variables:

```
LOGSEQ_API_TOKEN=your_token_here
LOGSEQ_API_URL=http://localhost:12315
```

## Development

### Building

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via `npm` with:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-logseq run mcp-logseq
```
