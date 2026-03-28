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
        self.delete_block(block_uuid)

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
            # Normalize properties for the createPage API.
            # Passing them as the 2nd argument stores them at the page entity level,
            # which is what Logseq queries via (page-property ...) and displays in
            # the page info panel. Using upsertBlockProperty on a content block
            # would create block-level properties instead, breaking queries.
            api_props: dict = {}
            if properties:
                for key, value in properties.items():
                    api_props[key] = self._normalize_property_value(key, value)

            # Step 1: Create the page with page-level properties
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.createPage",
                    "args": [title, api_props, {"createFirstBlock": True}],
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

                        logger.info(f"api_props={api_props!r}, will delete first block: {not api_props}")
                        if not api_props:
                            # No properties — remove the empty placeholder block
                            self.remove_block(first_block_uuid)
                        # When properties exist, keep the first block: createPage
                        # stores them there as a preBlock (tags:: val lines)
                else:
                    # Fallback: append blocks one by one if no first block
                    logger.warning("No first block found, using fallback append method")
                    for block in blocks:
                        self._append_block_recursive(title, block)

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

        # Append this block, nested under parent if available
        if parent_uuid:
            result = self.insert_block_as_child(parent_uuid, content, properties)
        else:
            result = self.append_block_in_page(page_name, content, properties)
        block_uuid = result.get("uuid") if result else None

        # Recursively append children under this block
        for child in children:
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
            if properties:
                if mode == "append":
                    existing_props = self._get_page_level_properties(page_name)
                    merged_props = {**existing_props, **properties}
                    self._set_page_level_properties(page_name, merged_props)
                    results.append(("properties", merged_props))
                else:
                    # Replace mode - set only the new properties
                    self._set_page_level_properties(page_name, properties)
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

    def _get_page_level_properties(self, page_name: str) -> dict:
        """
        Get page-level properties from the page entity (not from the first block).

        Uses getPage which returns the page entity with its page-level properties.
        """
        url = self.get_base_url()
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"method": "logseq.Editor.getPage", "args": [page_name]},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            page = response.json()
            if page and isinstance(page, dict):
                return page.get("properties", {}) or {}
            return {}
        except Exception as e:
            logger.warning(f"Could not get page-level properties for '{page_name}': {e}")
            return {}

    def _set_page_level_properties(self, page_name: str, properties: dict) -> None:
        """
        Set page-level properties via the setPageProperties API.

        Unlike upsertBlockProperty (which sets block-level properties), this
        stores properties at the page entity level, making them visible in the
        page info panel and queryable via (page-property ...).
        """
        url = self.get_base_url()
        api_props = {
            k: self._normalize_property_value(k, v) for k, v in properties.items()
        }
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.setPageProperties",
                    "args": [page_name, api_props],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            logger.info(f"Set {len(properties)} page-level properties on '{page_name}'")
        except Exception as e:
            logger.error(f"Could not set page-level properties for '{page_name}': {e}")
            raise

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

    # =========================================================================
    # DB-mode Property Methods (Datascript)
    # =========================================================================

    def datascript_query(self, query: str) -> list[list]:
        """Execute a raw Datascript query against the Logseq database.

        Args:
            query: Datalog query string (e.g. '[:find ?a ?v :where [101 ?a ?v]]')

        Returns:
            List of result tuples, e.g. [["title", "My Page"], [":db/ident", ":logseq..."]]
            Each inner list corresponds to the :find clause bindings.
        """
        url = self.get_base_url()
        logger.debug(f"Executing datascript query")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.DB.datascriptQuery",
                    "args": [query],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error executing datascript query: {str(e)}")
            raise

    def get_block_db_properties(self, block_id: int) -> dict[str, str]:
        """Get DB-mode class properties for a block.

        In Logseq DB-mode, class properties are stored as :user.property/*
        attributes on the block entity, with values referencing other entities.

        Args:
            block_id: The numeric ID of the block

        Returns:
            Dict of {property_title: value_title}
        """
        # Get all attributes and their values for this block
        query = f'[:find ?a ?v :where [{block_id} ?a ?v]]'
        try:
            attrs = self.datascript_query(query)
        except Exception:
            return {}

        user_props = {}
        for attr, val in attrs:
            if isinstance(attr, str) and attr.startswith(":user.property/"):
                user_props[attr] = val

        if not user_props:
            return {}

        # Resolve property display names and value titles
        result = {}
        for ident, val_id in user_props.items():
            # Get property display name via :db/ident lookup
            prop_name = self._resolve_entity_title_by_ident(ident) or ident

            # Get value title (val_id is an entity reference in DB-mode)
            if isinstance(val_id, int):
                val_title = self._resolve_entity_title(val_id) or str(val_id)
            else:
                val_title = str(val_id)

            result[prop_name] = val_title

        return result

    def _resolve_entity_title_by_ident(self, ident: str) -> str | None:
        """Resolve a :db/ident to its entity's title."""
        query = f'[:find ?id :where [?id :db/ident {ident}]]'
        try:
            result = self.datascript_query(query)
            if result:
                return self._resolve_entity_title(result[0][0])
        except Exception:
            pass
        return None

    def _resolve_entity_title(self, entity_id: int) -> str | None:
        """Get the title of an entity by its numeric ID."""
        query = f'[:find ?a ?v :where [{entity_id} ?a ?v]]'
        try:
            attrs = self.datascript_query(query)
            for attr, val in attrs:
                if attr == "title":
                    return str(val)
        except Exception:
            pass
        return None

    def _resolve_idents_batch(self, idents: set[str]) -> dict[str, int]:
        """Resolve multiple :db/ident values to their entity IDs in one query.

        Args:
            idents: Set of ident strings (e.g. {":user.property/status-abc"})

        Returns:
            Dict of {ident: entity_id}
        """
        if not idents:
            return {}
        or_clauses = " ".join(f'[?id :db/ident {ident}]' for ident in idents)
        query = f'[:find ?id ?ident :where (or {or_clauses}) [?id :db/ident ?ident]]'
        try:
            result = self.datascript_query(query)
            return {ident: eid for eid, ident in result if isinstance(ident, str)}
        except Exception:
            logger.warning("Batch ident resolution failed, falling back to individual queries")
            # Fallback: resolve one by one
            mapping = {}
            for ident in idents:
                try:
                    r = self.datascript_query(f'[:find ?id :where [?id :db/ident {ident}]]')
                    if r:
                        mapping[ident] = r[0][0]
                except Exception:
                    pass
            return mapping

    def _resolve_titles_batch(self, entity_ids: set[int]) -> dict[int, str]:
        """Resolve titles for multiple entities in a single query.

        Args:
            entity_ids: Set of numeric entity IDs

        Returns:
            Dict of {entity_id: title}
        """
        if not entity_ids:
            return {}
        or_clauses = " ".join(f'[{eid} ?a ?v]' for eid in entity_ids)
        query = f'[:find ?eid ?a ?v :where (or {or_clauses})]'
        try:
            results = self.datascript_query(query)
            titles = {}
            for eid, attr, val in results:
                if attr == "title":
                    titles[eid] = str(val)
            return titles
        except Exception:
            logger.warning("Batch title resolution failed, falling back to individual queries")
            # Fallback: resolve one by one
            titles = {}
            for eid in entity_ids:
                title = self._resolve_entity_title(eid)
                if title:
                    titles[eid] = title
            return titles

    def get_blocks_db_properties(self, blocks: list[dict]) -> dict[str, dict[str, str]]:
        """Get DB-mode properties for a list of blocks (from getPageBlocksTree).

        Batched approach to minimize API round-trips:
        1. Per block: query attributes (1 call per block)
        2. Batch resolve all :user.property/* idents to entity IDs (1 call)
        3. Batch resolve all entity titles (property names + values) (1 call)

        Args:
            blocks: List of block dicts from getPageBlocksTree

        Returns:
            Dict of {block_uuid: {property_title: value_title}}
        """
        # Phase 1: collect all block attributes (1 query per block)
        block_props: dict[str, dict[str, Any]] = {}  # uuid -> {ident: val}

        def collect_attrs(block_list: list[dict]) -> None:
            for block in block_list:
                block_id = block.get("id")
                block_uuid = str(block.get("uuid", ""))
                if block_id and block_uuid:
                    query = f'[:find ?a ?v :where [{block_id} ?a ?v]]'
                    try:
                        attrs = self.datascript_query(query)
                    except Exception:
                        attrs = []
                    user_props = {}
                    for attr, val in attrs:
                        if isinstance(attr, str) and attr.startswith(":user.property/"):
                            user_props[attr] = val
                    if user_props:
                        block_props[block_uuid] = user_props
                collect_attrs(block.get("children", []))

        collect_attrs(blocks)

        if not block_props:
            return {}

        # Phase 2: batch resolve all unique idents to entity IDs (1 query)
        all_idents = set()
        for props in block_props.values():
            all_idents.update(props.keys())

        ident_to_eid = self._resolve_idents_batch(all_idents)

        # Phase 3: collect all entity IDs needing title resolution
        entity_ids_to_resolve = set(ident_to_eid.values())
        for props in block_props.values():
            for val in props.values():
                if isinstance(val, int):
                    entity_ids_to_resolve.add(val)

        # Batch resolve all titles (1 query)
        titles = self._resolve_titles_batch(entity_ids_to_resolve)

        # Phase 4: assemble results using the resolved titles
        result = {}
        for block_uuid, props in block_props.items():
            resolved = {}
            for ident, val in props.items():
                # Property name: ident -> entity ID -> title
                prop_eid = ident_to_eid.get(ident)
                prop_name = titles.get(prop_eid) if prop_eid else None
                prop_name = prop_name or ident

                # Value: entity ref -> title, or string as-is
                if isinstance(val, int):
                    val_title = titles.get(val) or str(val)
                else:
                    val_title = str(val)

                resolved[prop_name] = val_title
            if resolved:
                result[block_uuid] = resolved

        return result

    def resolve_property_ident(self, property_name: str) -> str | None:
        """Look up the :user.property/* ident for a property by its display name.

        Uses a two-step approach since DB-mode datascript queries cannot filter
        on string attributes directly.

        Args:
            property_name: The human-readable property name (e.g. "Content status")

        Returns:
            The ident string (e.g. ":user.property/Contentstatus-oa99RD2-") or None
        """
        # Get all user property entities
        query = '[:find ?id ?ident :where [?id :db/ident ?ident]]'
        try:
            result = self.datascript_query(query)
            # Filter for :user.property/* idents
            for entity_id, ident in result:
                if isinstance(ident, str) and ident.startswith(":user.property/"):
                    title = self._resolve_entity_title(entity_id)
                    if title and title.lower() == property_name.lower():
                        return ident
        except Exception:
            pass
        return None

    def get_block(self, block_uuid: str, include_children: bool = True) -> Any:
        """Get a LogSeq block by UUID, optionally including its children tree.

        Args:
            block_uuid: UUID of the block to retrieve.
            include_children: Whether to include nested children (default True).

        Returns:
            Block dict with content, properties, uuid, children, etc.
        """
        url = self.get_base_url()
        logger.info(f"Getting block '{block_uuid}' (children={include_children})")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getBlock",
                    "args": [block_uuid, {"includeChildren": include_children}],
                },
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            if result is None:
                raise ValueError(f"Block '{block_uuid}' not found")

            logger.info(f"Successfully retrieved block '{block_uuid}'")
            return result

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error getting block '{block_uuid}': {str(e)}")
            raise

    def delete_block(self, block_uuid: str) -> Any:
        """Delete a LogSeq block by UUID."""
        url = self.get_base_url()
        logger.info(f"Deleting block '{block_uuid}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.removeBlock",
                    "args": [block_uuid]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully deleted block '{block_uuid}'")
            return result

        except Exception as e:
            logger.error(f"Error deleting block '{block_uuid}': {str(e)}")
            raise

    def update_block(self, block_uuid: str, content: str) -> Any:
        """Update a LogSeq block's content by UUID."""
        url = self.get_base_url()
        logger.info(f"Updating block '{block_uuid}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.updateBlock",
                    "args": [block_uuid, content]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully updated block '{block_uuid}'")
            return result

        except Exception as e:
            logger.error(f"Error updating block '{block_uuid}': {str(e)}")
            raise

    def query_dsl(self, query: str) -> Any:
        """Execute a Logseq DSL query to search pages and blocks.

        Args:
            query: Logseq DSL query string (e.g., '(page-property status active)')

        Returns:
            List of matching pages/blocks from the query
        """
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
            logger.error(f"Error executing DSL query: {str(e)}")
            raise

    def get_pages_from_namespace(self, namespace: str) -> Any:
        """Get all pages within a namespace (flat list)."""
        url = self.get_base_url()
        logger.info(f"Getting pages from namespace '{namespace}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPagesFromNamespace",
                    "args": [namespace]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting pages from namespace: {str(e)}")
            raise

    def get_pages_tree_from_namespace(self, namespace: str) -> Any:
        """Get pages within a namespace as a tree structure."""
        url = self.get_base_url()
        logger.info(f"Getting pages tree from namespace '{namespace}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPagesTreeFromNamespace",
                    "args": [namespace]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting pages tree from namespace: {str(e)}")
            raise

    def rename_page(self, old_name: str, new_name: str) -> Any:
        """Rename a page and update all references."""
        url = self.get_base_url()
        logger.info(f"Renaming page '{old_name}' to '{new_name}'")

        try:
            # Validate old page exists
            existing_pages = self.list_pages()
            page_names = [p.get("originalName") or p.get("name") for p in existing_pages]

            if old_name not in page_names:
                raise ValueError(f"Page '{old_name}' does not exist")

            if new_name in page_names:
                raise ValueError(f"Page '{new_name}' already exists")

            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.renamePage",
                    "args": [old_name, new_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            # renamePage returns null on success
            if response.text and response.text.strip() and response.text.strip() != 'null':
                return response.json()
            return None

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error renaming page: {str(e)}")
            raise

    def get_page_linked_references(self, page_name: str) -> Any:
        """Get all pages and blocks that reference this page (backlinks)."""
        url = self.get_base_url()
        logger.info(f"Getting backlinks for page '{page_name}'")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={
                    "method": "logseq.Editor.getPageLinkedReferences",
                    "args": [page_name]
                },
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error getting backlinks: {str(e)}")
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
