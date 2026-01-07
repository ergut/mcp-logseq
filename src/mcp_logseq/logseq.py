import requests
import logging
from typing import Any

logger = logging.getLogger("mcp-logseq")


class LogSeq:
    def __init__(
        self,
        api_key: str,
        protocol: str = "http",
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
        return f"{self.protocol}://{self.host}:{self.port}/api"

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

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
                    "args": [title, {}, {"createFirstBlock": True}],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
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
                        "args": [title, content],
                    },
                    verify=self.verify_ssl,
                    timeout=self.timeout,
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
                json={"method": "logseq.Editor.getAllPages", "args": []},
                verify=self.verify_ssl,
                timeout=self.timeout,
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
                json={"method": "logseq.Editor.getPage", "args": [page_name]},
                verify=self.verify_ssl,
                timeout=self.timeout,
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
                json={"method": "logseq.Editor.getPageBlocksTree", "args": [page_name]},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            blocks = response.json()

            # Step 3: Extract page properties from first block
            # In Logseq, page properties are stored in the first block
            properties = {}
            if blocks and len(blocks) > 0:
                properties = blocks[0].get("properties", {})

            return {
                "page": {**page_info, "properties": properties},
                "blocks": blocks or [],
            }

        except Exception as e:
            logger.error(f"Error getting page content: {str(e)}")
            raise

    def search_content(self, query: str, options: dict | None = None) -> Any:
        """Search for content across LogSeq pages and blocks."""
        url = self.get_base_url()
        logger.info(f"Searching for '{query}'")

        # Default search options
        search_options = options or {}

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.search", "args": [query, search_options]},
                verify=self.verify_ssl,
                timeout=self.timeout,
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
            page_names = [
                p.get("originalName") or p.get("name")
                for p in existing_pages
                if p.get("originalName") or p.get("name")
            ]

            if page_name not in page_names:
                raise ValueError(f"Page '{page_name}' does not exist")

            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.deletePage", "args": [page_name]},
                verify=self.verify_ssl,
                timeout=self.timeout,
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

    # =========================================================================
    # Block-Level API Methods
    # =========================================================================

    def get_page_blocks(self, page_name: str) -> list[dict]:
        """
        Get all root-level blocks for a page.

        Args:
            page_name: Name of the page

        Returns:
            List of block entities with UUIDs
        """
        url = self.get_base_url()
        logger.info(f"Getting blocks for page '{page_name}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.getPageBlocksTree", "args": [page_name]},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json() or []

        except Exception as e:
            logger.error(f"Error getting page blocks: {str(e)}")
            raise

    def remove_block(self, block_uuid: str) -> None:
        """
        Remove a single block by UUID.

        Args:
            block_uuid: UUID of block to remove
        """
        url = self.get_base_url()
        logger.debug(f"Removing block '{block_uuid}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.removeBlock", "args": [block_uuid]},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()

        except Exception as e:
            logger.error(f"Error removing block '{block_uuid}': {str(e)}")
            raise

    def clear_page_content(self, page_name: str) -> None:
        """
        Remove all blocks from a page.

        Args:
            page_name: Name of the page to clear
        """
        logger.info(f"Clearing content from page '{page_name}'")

        blocks = self.get_page_blocks(page_name)
        for block in blocks:
            block_uuid = block.get("uuid")
            if block_uuid:
                self.remove_block(block_uuid)

        logger.info(f"Cleared {len(blocks)} blocks from page '{page_name}'")

    def insert_batch_block(
        self, src_block: str, blocks: list[dict], sibling: bool = True
    ) -> Any:
        """
        Insert multiple blocks with hierarchy at once.

        Uses Logseq's insertBatchBlock API to insert a tree of blocks.

        Args:
            src_block: UUID of anchor block (blocks will be inserted after this)
            blocks: List of IBatchBlock dicts with 'content', optional 'children',
                    and optional 'properties'
            sibling: If True, insert as siblings of src_block;
                     if False, insert as children

        Returns:
            List of created block entities
        """
        url = self.get_base_url()
        logger.info(f"Inserting batch of {len(blocks)} blocks")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.insertBatchBlock",
                    "args": [src_block, blocks, {"sibling": sibling}],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully inserted batch blocks")
            return result

        except Exception as e:
            logger.error(f"Error inserting batch blocks: {str(e)}")
            raise

    def append_block_in_page(
        self, page_name: str, content: str, properties: dict | None = None
    ) -> dict:
        """
        Append a single block to the end of a page.

        Args:
            page_name: Name of the page
            content: Block content
            properties: Optional block properties

        Returns:
            Created block entity
        """
        url = self.get_base_url()
        logger.debug(f"Appending block to page '{page_name}'")

        try:
            args: list[Any] = [page_name, content]
            if properties:
                args.append({"properties": properties})

            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.appendBlockInPage", "args": args},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error appending block to page: {str(e)}")
            raise

    def create_page_with_blocks(
        self, title: str, blocks: list[dict], properties: dict | None = None
    ) -> dict:
        """
        Create a new page and populate it with blocks.

        This is the improved version of create_page that properly handles
        block hierarchy using insertBatchBlock.

        Args:
            title: Page title
            blocks: List of IBatchBlock dicts (from parser)
            properties: Optional page properties

        Returns:
            Created page entity
        """
        url = self.get_base_url()
        logger.info(f"Creating page '{title}' with {len(blocks)} blocks")

        try:
            # Step 1: Create the page without properties (properties will be set on first block later)
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.createPage",
                    "args": [title, {}, {"createFirstBlock": True}],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            page_result = response.json()

            # Step 2: If we have blocks to insert, get the first block and use it as anchor
            if blocks:
                page_blocks = self.get_page_blocks(title)

                if page_blocks and len(page_blocks) > 0:
                    first_block_uuid = page_blocks[0].get("uuid")

                    if first_block_uuid:
                        # Insert all blocks as siblings after the first block
                        self.insert_batch_block(first_block_uuid, blocks, sibling=True)

                        # Remove the empty first block that was auto-created
                        self.remove_block(first_block_uuid)
                else:
                    # Fallback: append blocks one by one if no first block
                    logger.warning("No first block found, using fallback append method")
                    for block in blocks:
                        self._append_block_recursive(title, block)

            # Step 3: Set properties on the first block if provided
            # Properties must be set AFTER blocks are inserted to ensure they're on the correct block
            if properties:
                self._update_page_properties(title, properties)

            logger.info(f"Successfully created page '{title}' with blocks")
            return page_result

        except Exception as e:
            logger.error(f"Error creating page with blocks: {str(e)}")
            raise

    def _append_block_recursive(
        self, page_name: str, block: dict, parent_uuid: str | None = None
    ) -> None:
        """
        Recursively append a block and its children to a page.

        Fallback method when insertBatchBlock is not available.
        """
        content = block.get("content", "")
        properties = block.get("properties")
        children = block.get("children", [])

        # Append this block
        result = self.append_block_in_page(page_name, content, properties)
        block_uuid = result.get("uuid") if result else None

        # Append children if any (would need insertBlock with parent)
        # For now, just append them at root level with indentation marker
        for child in children:
            # Note: This is a simplified fallback - proper nesting requires insertBlock
            self._append_block_recursive(page_name, child, block_uuid)

    def update_page_with_blocks(
        self,
        page_name: str,
        blocks: list[dict],
        properties: dict | None = None,
        mode: str = "append",
    ) -> dict:
        """
        Update a page with new blocks.

        Args:
            page_name: Name of the page to update
            blocks: List of IBatchBlock dicts (from parser)
            properties: Optional page properties to set
            mode: "append" to add after existing content, "replace" to clear first

        Returns:
            Dict with update results
        """
        logger.info(
            f"Updating page '{page_name}' with {len(blocks)} blocks (mode={mode})"
        )

        # Validate page exists
        existing_pages = self.list_pages()
        page_names = [
            p.get("originalName") or p.get("name")
            for p in existing_pages
            if p.get("originalName") or p.get("name")
        ]

        if page_name not in page_names:
            raise ValueError(f"Page '{page_name}' does not exist")

        results: list[tuple[str, Any]] = []

        try:
            # Handle replace mode - clear existing content
            if mode == "replace":
                self.clear_page_content(page_name)
                results.append(("cleared", True))

            # Insert new blocks FIRST, then set properties
            if blocks:
                if mode == "replace":
                    # After clearing, we need to add a first block to use as anchor
                    first_block = blocks[0]
                    anchor = self.append_block_in_page(
                        page_name,
                        first_block.get("content", ""),
                        first_block.get("properties"),
                    )
                    anchor_uuid = anchor.get("uuid") if anchor else None

                    # Insert children of first block if any
                    if anchor_uuid and first_block.get("children"):
                        self.insert_batch_block(
                            anchor_uuid,
                            first_block["children"],
                            sibling=False,  # Insert as children
                        )

                    # Insert remaining blocks as siblings
                    if len(blocks) > 1 and anchor_uuid:
                        self.insert_batch_block(anchor_uuid, blocks[1:], sibling=True)

                    results.append(("blocks_replaced", len(blocks)))
                else:
                    # Append mode - get last block and insert after it
                    page_blocks = self.get_page_blocks(page_name)

                    if page_blocks:
                        last_block_uuid = page_blocks[-1].get("uuid")
                        if last_block_uuid:
                            self.insert_batch_block(
                                last_block_uuid, blocks, sibling=True
                            )
                            results.append(("blocks_appended", len(blocks)))
                    else:
                        # No existing blocks, just append
                        for block in blocks:
                            self._append_block_recursive(page_name, block)
                        results.append(("blocks_appended", len(blocks)))

            # Update properties AFTER blocks are inserted/replaced
            # This ensures properties are always set on the correct first block
            if properties:
                # For append mode, merge with existing properties
                # For replace mode, replace all properties
                if mode == "append":
                    existing_props = self._get_page_properties(page_name)
                    merged_props = {**existing_props, **properties}
                    self._update_page_properties(page_name, merged_props)
                    results.append(("properties", merged_props))
                else:
                    # Replace mode - set only the new properties
                    self._update_page_properties(page_name, properties)
                    results.append(("properties", properties))

            return {"updates": results, "page": page_name}

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating page with blocks: {str(e)}")
            raise

    def _get_page_properties(self, page_name: str) -> dict:
        """
        Get current page properties from the first block.

        Returns:
            Dict of current page properties, or empty dict if none found
        """
        page_blocks = self.get_page_blocks(page_name)
        if not page_blocks:
            return {}

        first_block = page_blocks[0]
        return first_block.get("properties", {})

    def _normalize_property_value(self, key: str, value: Any) -> Any:
        """
        Normalize property values for Logseq's upsertBlockProperty API.

        Handles special cases:
        - tags/aliases as dict with boolean values -> convert to array of keys
        - Other dicts remain as-is (for nested properties)

        Args:
            key: Property name
            value: Property value

        Returns:
            Normalized value suitable for Logseq
        """
        # Special handling for tags and aliases - convert dict to array
        if key in ("tags", "alias", "aliases") and isinstance(value, dict):
            # Extract keys where value is truthy (typically true for tags)
            return [k for k, v in value.items() if v]

        return value

    def _update_page_properties(self, page_name: str, properties: dict) -> None:
        """
        Update page properties by setting them on the first block.

        In Logseq, page properties are stored in the first block of the page
        using the `property:: value` syntax. This method updates properties
        by calling upsertBlockProperty on the first block.
        """
        # Get first block of the page
        page_blocks = self.get_page_blocks(page_name)
        if not page_blocks:
            logger.warning(f"Page '{page_name}' has no blocks, cannot set properties")
            return

        first_block_uuid = page_blocks[0].get("uuid")
        if not first_block_uuid:
            logger.warning(f"Could not get first block UUID for page '{page_name}'")
            return

        # Set each property using upsertBlockProperty
        for key, value in properties.items():
            normalized_value = self._normalize_property_value(key, value)
            self._upsert_block_property(first_block_uuid, key, normalized_value)

        logger.info(f"Updated {len(properties)} properties on page '{page_name}'")

    def _upsert_block_property(self, block_uuid: str, key: str, value: Any) -> None:
        """
        Set a property on a block using Logseq's upsertBlockProperty API.

        Args:
            block_uuid: UUID of the block to update
            key: Property key
            value: Property value
        """
        url = self.get_base_url()

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.upsertBlockProperty",
                    "args": [block_uuid, key, value],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to set property '{key}' on block {block_uuid}: {e}")
            raise
