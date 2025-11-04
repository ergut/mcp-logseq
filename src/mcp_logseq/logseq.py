import requests
import logging
from typing import Any

logger = logging.getLogger("mcp-logseq")

class LogSeq():
    def __init__(
            self, 
            api_key: str,
            protocol: str = 'http',
            host: str = "127.0.0.1",
            port: int = 12315,
            verify_ssl: bool = False,
        ):
        self.api_key = api_key
        self.protocol = protocol
        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = (3, 6)

    def get_base_url(self) -> str:
        return f'{self.protocol}://{self.host}:{self.port}/api'
    
    def _get_headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}'
        }

    def create_page(self, title: str, content: str = "") -> Any:
        """Create a new LogSeq page with specified title and content."""
        url = self.get_base_url()
        logger.info(f"Creating page '{title}'")
        
        try:
            # Step 1: Create the page
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.createPage",
                    "args": [title, {}, {"createFirstBlock": True}]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            page_result = response.json()
            
            # Step 2: Add content if provided
            if content and content.strip():
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json={
                        "method": "logseq.Editor.appendBlockInPage",
                        "args": [title, content]
                    },
                    verify=self.verify_ssl,
                    timeout=self.timeout
                )
                response.raise_for_status()
            
            return page_result

        except Exception as e:
            logger.error(f"Error creating page: {str(e)}")
            raise
            
    def list_pages(self) -> Any:
        """List all pages in the LogSeq graph."""
        url = self.get_base_url()
        logger.info("Listing pages")
        
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getAllPages",
                    "args": []
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error listing pages: {str(e)}")
            raise
    
    def get_page_content(self, page_name: str) -> Any:
        """Get content of a LogSeq page including metadata and block content."""
        url = self.get_base_url()
        logger.info(f"Getting content for page '{page_name}'")
        
        try:
            # Step 1: Get page metadata (includes UUID)
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPage",
                    "args": [page_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            page_info = response.json()
            
            if not page_info:
                logger.error(f"Page '{page_name}' not found")
                return None
                
            # Step 2: Get page blocks using the page name
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPageBlocksTree",
                    "args": [page_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            blocks = response.json()
            
            # Step 3: Get page properties
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPageProperties",
                    "args": [page_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            properties = response.json() or {}
            
            return {
                "page": {
                    **page_info,
                    "properties": properties
                },
                "blocks": blocks or []
            }
            
        except Exception as e:
            logger.error(f"Error getting page content: {str(e)}")
            raise

    def search_content(self, query: str, options: dict = None) -> Any:
        """Search for content across LogSeq pages and blocks."""
        url = self.get_base_url()
        logger.info(f"Searching for '{query}'")
        
        # Default search options
        search_options = options or {}
        
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.search",
                    "args": [query, search_options]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error searching content: {str(e)}")
            raise
    
    def delete_page(self, page_name: str) -> Any:
        """Delete a LogSeq page by name."""
        url = self.get_base_url()
        logger.info(f"Deleting page '{page_name}'")
        
        try:
            # Pre-delete validation: verify page exists
            existing_pages = self.list_pages()
            page_names = [p.get("originalName") or p.get("name") for p in existing_pages if p.get("originalName") or p.get("name")]
            
            if page_name not in page_names:
                raise ValueError(f"Page '{page_name}' does not exist")
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.deletePage",
                    "args": [page_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully deleted page '{page_name}'")
            return result

        except ValueError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            logger.error(f"Error deleting page '{page_name}': {str(e)}")
            raise
    
    def update_page(self, page_name: str, content: str = None, properties: dict = None) -> Any:
        """Update a LogSeq page with new content and/or properties."""
        url = self.get_base_url()
        logger.info(f"Updating page '{page_name}'")
        
        try:
            # Pre-update validation: verify page exists
            existing_pages = self.list_pages()
            page_names = [p.get("originalName") or p.get("name") for p in existing_pages if p.get("originalName") or p.get("name")]
            
            if page_name not in page_names:
                raise ValueError(f"Page '{page_name}' does not exist")
            
            results = []
            
            # Update properties if provided
            if properties:
                logger.debug(f"Updating properties for page '{page_name}': {properties}")
                try:
                    response = requests.post(
                        url,
                        headers=self._get_headers(),
                        json={
                            "method": "logseq.Editor.updatePage",
                            "args": [page_name, properties]
                        },
                        verify=self.verify_ssl,
                        timeout=self.timeout
                    )
                    response.raise_for_status()
                    prop_result = response.json()
                    results.append(("properties", prop_result))
                except Exception as e:
                    logger.warning(f"Failed to update properties with updatePage, trying setPageProperties: {str(e)}")
                    # Fallback to setPageProperties
                    response = requests.post(
                        url,
                        headers=self._get_headers(),
                        json={
                            "method": "logseq.Editor.setPageProperties",
                            "args": [page_name, properties]
                        },
                        verify=self.verify_ssl,
                        timeout=self.timeout
                    )
                    response.raise_for_status()
                    prop_result = response.json()
                    results.append(("properties_fallback", prop_result))
            
            # Update content if provided
            if content is not None:
                logger.debug(f"Updating content for page '{page_name}'")
                # Strategy: Get existing blocks and update them, or add new content
                # For now, we'll use appendBlockInPage to add new content
                # TODO: In future, implement block-level updates for more sophisticated content management
                
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json={
                        "method": "logseq.Editor.appendBlockInPage",
                        "args": [page_name, content]
                    },
                    verify=self.verify_ssl,
                    timeout=self.timeout
                )
                response.raise_for_status()
                content_result = response.json()
                results.append(("content", content_result))
            
            logger.info(f"Successfully updated page '{page_name}'")
            return {"updates": results, "page": page_name}

        except ValueError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            logger.error(f"Error updating page '{page_name}': {str(e)}")
            raise

    def insert_block_as_child(
        self,
        parent_block_uuid: str,
        content: str,
        properties: dict = None,
        sibling: bool = False
    ) -> Any:
        """Insert a new block as a child of an existing block, enabling nested block structures."""
        url = self.get_base_url()
        logger.info(f"Inserting block as {'sibling' if sibling else 'child'} of {parent_block_uuid}")

        try:
            options = {
                "sibling": sibling
            }

            if properties:
                options["properties"] = properties

            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.insertBlock",
                    "args": [parent_block_uuid, content, options]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"Successfully inserted block under {parent_block_uuid}")
            return result

        except Exception as e:
            logger.error(f"Error inserting nested block: {str(e)}")
            raise
