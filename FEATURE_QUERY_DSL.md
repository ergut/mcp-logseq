# Feature: Query DSL (Search by Properties)

## Contexto

O Logseq possui um poderoso sistema de queries DSL que permite buscar páginas e blocos por propriedades, tags, e combinações lógicas. Atualmente o MCP não expõe essa capacidade, impossibilitando buscas como:

- "Todas as páginas com `status:: active`"
- "Todos os clientes (`type:: customer`) que estão ativos"
- "Blocos marcados como TODO criados esta semana"

## Problema

Nenhuma tool atual permite buscar por propriedades/metadados:

| Tool | Busca por propriedade? |
|------|------------------------|
| `list_pages` | ❌ Lista tudo, sem filtro |
| `search` | ❌ Full-text apenas |
| `get_page_content` | ❌ Exibe uma página, não busca |

Para encontrar páginas por propriedade hoje, seria necessário listar todas as páginas e chamar `get_page_content` em cada uma — inviável.

## Solução Proposta

Implementar duas tools complementares:

### 1. `query` (Query DSL genérica)

Executa queries DSL arbitrárias do Logseq. Máxima flexibilidade para usuários avançados.

**API Logseq:**
```json
{
  "method": "logseq.DB.q",
  "args": ["(page-property service mentorship)"]
}
```

**Tool Schema:**
```python
Tool(
    name="query",
    description="Execute a Logseq DSL query to search pages and blocks. Supports property queries, tag queries, task queries, and logical combinations.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Logseq DSL query string (e.g., '(page-property status active)', '(and (task todo) (page [[Project]])')"
            }
        },
        "required": ["query"]
    }
)
```

**Exemplos de queries DSL:**

```clojure
;; Páginas com propriedade específica
(page-property service mentorship)
(page-property status "in progress")

;; Páginas com qualquer valor para uma propriedade
(page-property type)

;; Combinações lógicas
(and (page-property type customer) (page-property status active))
(or (page-property priority high) (page-property priority urgent))

;; Blocos com tags
(page-tags [[meeting]])

;; Tasks
(task todo)
(task now later)
(and (task todo) (page [[Projects]]))

;; Blocos com propriedades
(property status done)

;; Between dates (para journals)
(between [[Dec 1st, 2024]] [[Dec 15th, 2024]])
```

---

### 2. `find_pages_by_property` (Busca simplificada)

Interface amigável para o caso de uso mais comum: buscar páginas por propriedade.

**Tool Schema:**
```python
Tool(
    name="find_pages_by_property",
    description="Find all pages that have a specific property, optionally filtered by value. Simpler alternative to the full query DSL.",
    inputSchema={
        "type": "object",
        "properties": {
            "property_name": {
                "type": "string",
                "description": "Name of the property to search for (e.g., 'status', 'type', 'service')"
            },
            "property_value": {
                "type": "string",
                "description": "Optional: specific value to match. If omitted, returns all pages that have this property."
            }
        },
        "required": ["property_name"]
    }
)
```

**Exemplos de uso:**

```
Input: {"property_name": "service", "property_value": "mentorship"}
Output:
Pages with property 'service = mentorship':

- Customer/Orienteme

Total: 1 page
```

```
Input: {"property_name": "type"}
Output:
Pages with property 'type':

- Customer/Orienteme (type: customer)
- Customer/InsideOut (type: customer)  
- Projects/Website (type: project)

Total: 3 pages
```

---

## Implementação

### Arquivo: `src/mcp_logseq/logseq.py`

```python
def query_dsl(self, query: str) -> Any:
    """Execute a Logseq DSL query."""
    url = self.get_base_url()
    logger.info(f"Executing DSL query: {query}")
    
    try:
        response = requests.post(
            url,
            headers=self._get_headers(),
            json={
                "method": "logseq.DB.q",
                "args": [query]
            },
            verify=self.verify_ssl,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        logger.error(f"Error executing query: {str(e)}")
        raise


def find_pages_by_property(self, property_name: str, property_value: str = None) -> Any:
    """Find pages by property name and optional value."""
    # Build the DSL query
    if property_value:
        # Escape quotes in value if needed
        escaped_value = property_value.replace('"', '\\"')
        query = f'(page-property {property_name} "{escaped_value}")'
    else:
        query = f'(page-property {property_name})'
    
    return self.query_dsl(query)
```

### Arquivo: `src/mcp_logseq/tools.py`

```python
class QueryToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("query")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Execute a Logseq DSL query to search pages and blocks. Supports property queries, tag queries, task queries, and logical combinations. See https://docs.logseq.com/#/page/queries for query syntax.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Logseq DSL query string (e.g., '(page-property status active)')"
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "query" not in args:
            raise RuntimeError("query argument required")

        query = args["query"]

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.query_dsl(query)
            
            if not result:
                return [TextContent(
                    type="text",
                    text=f"No results found for query: {query}"
                )]
            
            # Format results
            content_parts = []
            content_parts.append(f"# Query Results\n")
            content_parts.append(f"**Query:** `{query}`\n")
            
            # Results can be pages or blocks
            for i, item in enumerate(result, 1):
                if isinstance(item, dict):
                    # Could be a page or block
                    name = item.get('originalName') or item.get('name') or item.get('content', '')[:50]
                    
                    # Get properties if available
                    props = item.get('propertiesTextValues', {})
                    props_str = ", ".join(f"{k}: {v}" for k, v in props.items()) if props else ""
                    
                    if props_str:
                        content_parts.append(f"{i}. **{name}** ({props_str})")
                    else:
                        content_parts.append(f"{i}. **{name}**")
                else:
                    content_parts.append(f"{i}. {item}")
            
            content_parts.append(f"\n---\n**Total: {len(result)} results**")
            
            return [TextContent(type="text", text="\n".join(content_parts))]
            
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Query failed: {str(e)}\n\nMake sure the query syntax is valid. See https://docs.logseq.com/#/page/queries"
            )]


class FindPagesByPropertyToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("find_pages_by_property")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Find all pages that have a specific property, optionally filtered by value.",
            inputSchema={
                "type": "object",
                "properties": {
                    "property_name": {
                        "type": "string",
                        "description": "Name of the property to search for (e.g., 'status', 'type', 'service')"
                    },
                    "property_value": {
                        "type": "string",
                        "description": "Optional: specific value to match"
                    }
                },
                "required": ["property_name"]
            }
        )

    def run_tool(self, args: dict) -> list[TextContent]:
        if "property_name" not in args:
            raise RuntimeError("property_name argument required")

        property_name = args["property_name"]
        property_value = args.get("property_value")

        try:
            api = logseq.LogSeq(api_key=api_key)
            result = api.find_pages_by_property(property_name, property_value)
            
            if not result:
                if property_value:
                    msg = f"No pages found with property '{property_name} = {property_value}'"
                else:
                    msg = f"No pages found with property '{property_name}'"
                return [TextContent(type="text", text=msg)]
            
            # Format results
            content_parts = []
            
            if property_value:
                content_parts.append(f"# Pages with '{property_name} = {property_value}'\n")
            else:
                content_parts.append(f"# Pages with property '{property_name}'\n")
            
            for item in result:
                if isinstance(item, dict):
                    name = item.get('originalName') or item.get('name', '<unknown>')
                    props = item.get('propertiesTextValues', {})
                    
                    # Show the property value if we searched without a specific value
                    if not property_value and property_name in props:
                        content_parts.append(f"- **{name}** ({property_name}: {props[property_name]})")
                    else:
                        content_parts.append(f"- **{name}**")
            
            content_parts.append(f"\n---\n**Total: {len(result)} pages**")
            
            return [TextContent(type="text", text="\n".join(content_parts))]
            
        except Exception as e:
            logger.error(f"Property search failed: {str(e)}")
            return [TextContent(
                type="text",
                text=f"❌ Search failed: {str(e)}"
            )]
```

### Arquivo: `src/mcp_logseq/server.py`

Registrar os novos handlers:

```python
add_tool_handler(tools.QueryToolHandler())
add_tool_handler(tools.FindPagesByPropertyToolHandler())
```

---

## Testes

### Testes Unitários (`tests/unit/test_tool_handlers.py`)

```python
def test_query_handler():
    handler = QueryToolHandler()
    assert handler.name == "query"
    
    tool = handler.get_tool_description()
    assert "query" in tool.inputSchema["properties"]
    assert "query" in tool.inputSchema["required"]


def test_find_pages_by_property_handler():
    handler = FindPagesByPropertyToolHandler()
    assert handler.name == "find_pages_by_property"
    
    tool = handler.get_tool_description()
    assert "property_name" in tool.inputSchema["properties"]
    assert "property_value" in tool.inputSchema["properties"]
    assert "property_name" in tool.inputSchema["required"]
    assert "property_value" not in tool.inputSchema["required"]
```

### Testes de Integração (`tests/integration/test_query.py`)

```python
import pytest
import os
from mcp_logseq.logseq import LogSeq

@pytest.mark.integration
class TestQueryIntegration:
    
    def test_query_dsl_page_property(self):
        """Test querying pages by property."""
        api = LogSeq(api_key=os.getenv("LOGSEQ_API_TOKEN"))
        
        # Setup - create a page with property
        api.create_page("TestQueryPage", "type:: test\nTest content")
        
        # Test
        result = api.query_dsl("(page-property type test)")
        
        # Verify
        assert result is not None
        page_names = [p.get('originalName') or p.get('name') for p in result if isinstance(p, dict)]
        assert "TestQueryPage" in page_names
        
        # Cleanup
        api.delete_page("TestQueryPage")
    
    def test_find_pages_by_property_with_value(self):
        """Test simplified property search with value."""
        api = LogSeq(api_key=os.getenv("LOGSEQ_API_TOKEN"))
        
        # Setup
        api.create_page("TestPropPage", "status:: active\nContent")
        
        # Test
        result = api.find_pages_by_property("status", "active")
        
        # Verify
        assert result is not None
        
        # Cleanup
        api.delete_page("TestPropPage")
    
    def test_find_pages_by_property_without_value(self):
        """Test simplified property search without value (any value)."""
        api = LogSeq(api_key=os.getenv("LOGSEQ_API_TOKEN"))
        
        # Setup - create pages with same property, different values
        api.create_page("TestPropA", "category:: alpha\nContent A")
        api.create_page("TestPropB", "category:: beta\nContent B")
        
        # Test - find all pages with 'category' property
        result = api.find_pages_by_property("category")
        
        # Verify - should find both
        assert result is not None
        assert len(result) >= 2
        
        # Cleanup
        api.delete_page("TestPropA")
        api.delete_page("TestPropB")
    
    def test_query_dsl_logical_combination(self):
        """Test query with AND/OR logic."""
        api = LogSeq(api_key=os.getenv("LOGSEQ_API_TOKEN"))
        
        # Setup
        api.create_page("TestLogicPage", "type:: customer\nstatus:: active\nContent")
        
        # Test - AND query
        result = api.query_dsl("(and (page-property type customer) (page-property status active))")
        
        # Verify
        assert result is not None
        
        # Cleanup
        api.delete_page("TestLogicPage")
```

---

## Documentação de Queries DSL

Incluir na descrição da tool ou em README:

### Sintaxe Básica

```clojure
;; Buscar páginas por propriedade
(page-property <nome> <valor>)
(page-property <nome>)           ;; qualquer valor

;; Buscar blocos por propriedade  
(property <nome> <valor>)

;; Combinações lógicas
(and <query1> <query2> ...)
(or <query1> <query2> ...)
(not <query>)

;; Tasks/TODOs
(task todo)
(task now later done)

;; Tags
(page-tags [[tag-name]])

;; Referências
(page [[Page Name]])

;; Datas (para journals)
(between [[Dec 1st, 2024]] [[Dec 15th, 2024]])
```

### Exemplos Práticos

```clojure
;; Todos os clientes ativos
(and (page-property type customer) (page-property status active))

;; Páginas de projeto com prioridade alta
(and (page-property type project) (page-property priority high))

;; TODOs não concluídos
(task todo now later)

;; Páginas modificadas em dezembro
(between [[Dec 1st, 2024]] [[Dec 31st, 2024]])
```

---

## Atualização do ROADMAP

Após implementação, adicionar a "Implemented Features":

```markdown
- ✅ Query System
  - `query` - Execute arbitrary DSL queries
  - `find_pages_by_property` - Simplified property search
```

---

## Referências

- [Logseq Queries Documentation](https://docs.logseq.com/#/page/queries)
- [Logseq Plugin API - IDBProxy](https://logseq.github.io/plugins/interfaces/IDBProxy.html)
- Método: `q<T>(dsl: string): Promise<T[]>` - Run a DSL query
