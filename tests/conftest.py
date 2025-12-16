import pytest
import responses
from unittest.mock import Mock, patch
from mcp_logseq.logseq import LogSeq
from mcp_logseq.tools import (
    CreatePageToolHandler,
    ListPagesToolHandler,
    GetPageContentToolHandler,
    DeletePageToolHandler,
    UpdatePageToolHandler,
    SearchToolHandler,
    GetPagesFromNamespaceToolHandler,
    GetPagesTreeFromNamespaceToolHandler,
    RenamePageToolHandler,
    GetPageBacklinksToolHandler
)

@pytest.fixture
def mock_api_key():
    """Provide a mock API key for testing."""
    return "test_api_key_12345"

@pytest.fixture
def logseq_client(mock_api_key):
    """Create a LogSeq client instance for testing."""
    return LogSeq(api_key=mock_api_key)

@pytest.fixture
def mock_logseq_responses():
    """Provide mock responses for LogSeq API calls."""
    return {
        "create_page_success": {
            "id": "page-123",
            "name": "Test Page",
            "originalName": "Test Page",
            "created": True
        },
        "list_pages_success": [
            {
                "id": "page-1",
                "name": "Page One", 
                "originalName": "Page One",
                "journal?": False
            },
            {
                "id": "page-2",
                "name": "Daily Journal",
                "originalName": "Daily Journal", 
                "journal?": True
            }
        ],
        "get_page_success": {
            "id": "page-123",
            "name": "Test Page",
            "originalName": "Test Page",
            "uuid": "uuid-123"
        },
        "get_page_blocks_success": [
            {
                "id": "block-1",
                "content": "This is block content",
                "properties": {}
            }
        ],
        "get_page_properties_success": {
            "tags": ["test", "example"],
            "priority": "high"
        },
        "search_success": {
            "blocks": [
                {
                    "block/content": "Search result content"
                }
            ],
            "pages": ["Matching Page"],
            "pages-content": [
                {
                    "block/snippet": "Snippet with search term"
                }
            ],
            "files": [],
            "has-more?": False
        },
        "get_pages_from_namespace_success": [
            {
                "id": "page-1",
                "name": "customer/insideout",
                "originalName": "Customer/InsideOut"
            },
            {
                "id": "page-2",
                "name": "customer/orienteme",
                "originalName": "Customer/Orienteme"
            }
        ],
        "get_pages_tree_from_namespace_success": [
            {
                "id": "page-1",
                "name": "projects/2024",
                "originalName": "Projects/2024",
                "children": [
                    {
                        "id": "page-2",
                        "name": "projects/2024/clienta",
                        "originalName": "Projects/2024/ClientA",
                        "children": []
                    },
                    {
                        "id": "page-3",
                        "name": "projects/2024/clientb",
                        "originalName": "Projects/2024/ClientB",
                        "children": []
                    }
                ]
            },
            {
                "id": "page-4",
                "name": "projects/archive",
                "originalName": "Projects/Archive",
                "children": []
            }
        ],
        "rename_page_success": None,
        "get_page_linked_references_success": [
            [
                {
                    "id": "page-1",
                    "name": "dec 15th, 2024",
                    "originalName": "Dec 15th, 2024"
                },
                [
                    {"content": "session [[Customer/Orienteme]]"},
                    {"content": "followup with [[Customer/Orienteme]] team"}
                ]
            ],
            [
                {
                    "id": "page-2",
                    "name": "projects/ai consulting",
                    "originalName": "Projects/AI Consulting"
                },
                [
                    {"content": "Active client: [[Customer/Orienteme]]"}
                ]
            ]
        ]
    }

@pytest.fixture
def tool_handlers():
    """Provide instances of all tool handlers for testing."""
    return {
        "create_page": CreatePageToolHandler(),
        "list_pages": ListPagesToolHandler(),
        "get_page_content": GetPageContentToolHandler(),
        "delete_page": DeletePageToolHandler(),
        "update_page": UpdatePageToolHandler(),
        "search": SearchToolHandler(),
        "get_pages_from_namespace": GetPagesFromNamespaceToolHandler(),
        "get_pages_tree_from_namespace": GetPagesTreeFromNamespaceToolHandler(),
        "rename_page": RenamePageToolHandler(),
        "get_page_backlinks": GetPageBacklinksToolHandler()
    }

@pytest.fixture
def mock_env_api_key(mock_api_key):
    """Mock the environment variable for API key."""
    with patch.dict('os.environ', {'LOGSEQ_API_TOKEN': mock_api_key}):
        yield mock_api_key