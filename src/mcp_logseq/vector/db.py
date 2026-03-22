"""
LanceDB wrapper for Logseq vector search.

Uses lancedb (optional dependency). Only imported when vector is configured.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_logseq.vector.types import LogseqChunk, SearchParams, SearchResult

logger = logging.getLogger("mcp-logseq.vector.db")

_TABLE_NAME = "chunks"


def _get_schema(dimensions: int):
    import pyarrow as pa
    return pa.schema([
        pa.field("id", pa.utf8()),
        pa.field("page", pa.utf8()),
        pa.field("text", pa.utf8()),
        pa.field("raw", pa.utf8()),
        pa.field("tags", pa.list_(pa.utf8())),
        pa.field("date", pa.utf8()),
        pa.field("properties", pa.utf8()),
        pa.field("block_index", pa.int32()),
        pa.field("vector", pa.list_(pa.float32(), dimensions)),
    ])


def _chunks_to_records(chunks: list[LogseqChunk]) -> list[dict]:
    return [
        {
            "id": c.id,
            "page": c.page,
            "text": c.text,
            "raw": c.raw,
            "tags": c.tags,
            "date": c.date or "",
            "properties": c.properties,
            "block_index": c.block_index,
            "vector": c.vector or [],
        }
        for c in chunks
        if c.vector is not None
    ]


def _row_to_result(row: dict, score: float) -> SearchResult:
    try:
        props = json.loads(row.get("properties", "{}"))
    except Exception:
        props = {}
    date_val = row.get("date") or None
    if date_val == "":
        date_val = None
    tags = row.get("tags", [])
    if tags is None:
        tags = []
    return SearchResult(
        page=row["page"],
        text=row["text"],
        raw=row["raw"],
        score=score,
        tags=list(tags),
        date=date_val,
        properties=props,
        chunk_index=row["block_index"],
    )


class VectorDB:
    def __init__(self, db, table, dimensions: int) -> None:
        self._db = db
        self._table = table
        self._dimensions = dimensions

    @classmethod
    def open(cls, db_path: str, dimensions: int) -> "VectorDB":
        import lancedb

        os.makedirs(db_path, exist_ok=True)
        db = lancedb.connect(db_path)
        table_names = db.table_names()
        logger.info(f"LanceDB at {db_path}: tables found = {table_names}")

        if _TABLE_NAME not in table_names:
            # Check if data directory exists but LanceDB can't read it (version mismatch)
            data_dir = Path(db_path) / f"{_TABLE_NAME}.lance"
            if data_dir.exists():
                logger.warning(
                    f"Data directory '{data_dir}' exists but LanceDB cannot read table "
                    f"'{_TABLE_NAME}'. This typically means the DB was written by a different "
                    f"LanceDB version. Run sync_vector_db with rebuild=true to re-index."
                )
            schema = _get_schema(dimensions)
            table = db.create_table(_TABLE_NAME, schema=schema)
            logger.info(f"Created new LanceDB table '{_TABLE_NAME}' with {dimensions} dims")
        else:
            table = db.open_table(_TABLE_NAME)
            logger.info(f"Opened existing LanceDB table '{_TABLE_NAME}'")

        return cls(db, table, dimensions)

    @classmethod
    def open_readonly(cls, db_path: str, dimensions: int) -> "VectorDB":
        """Open an existing LanceDB table for reading only.

        Unlike open(), this method:
        - Does not create directories or tables
        - Raises RuntimeError if the DB or table does not exist
        - Provides clear diagnostics for version mismatch
        """
        import lancedb

        if not Path(db_path).exists():
            raise RuntimeError(
                "Vector DB not initialized. Run sync_vector_db or logseq-sync --once first."
            )

        db = lancedb.connect(db_path)
        table_names = db.table_names()
        logger.info(f"LanceDB (read-only) at {db_path}: tables found = {table_names}")

        if _TABLE_NAME not in table_names:
            data_dir = Path(db_path) / f"{_TABLE_NAME}.lance"
            if data_dir.exists():
                raise RuntimeError(
                    f"Vector DB data exists at {data_dir} but cannot be read. "
                    f"Possible LanceDB version mismatch. "
                    f"Run logseq-sync --rebuild to re-index."
                )
            raise RuntimeError(
                "Vector DB not initialized. Run sync_vector_db or logseq-sync --once first."
            )

        table = db.open_table(_TABLE_NAME)
        logger.info(f"Opened existing LanceDB table '{_TABLE_NAME}' (read-only)")
        return cls(db, table, dimensions)

    def upsert(self, chunks: list[LogseqChunk]) -> None:
        if not chunks:
            return
        records = _chunks_to_records(chunks)
        if not records:
            return
        # Delete existing rows with same IDs, then insert
        ids = [r["id"] for r in records]
        id_list = ", ".join(f'"{i}"' for i in ids)
        try:
            self._table.delete(f"id IN ({id_list})")
        except Exception:
            pass  # Table may be empty
        self._table.add(records)
        logger.debug(f"Upserted {len(records)} chunks")

    def delete_by_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        id_list = ", ".join(f'"{i}"' for i in ids)
        try:
            self._table.delete(f"id IN ({id_list})")
            logger.debug(f"Deleted {len(ids)} chunks")
        except Exception as e:
            logger.warning(f"Delete failed: {e}")

    def search(self, params: SearchParams) -> list[SearchResult]:
        if not params.query_vector:
            return []

        top_k = params.top_k

        try:
            if params.mode == "keyword":
                return self._keyword_search(params, top_k)
            elif params.mode == "vector":
                return self._vector_search(params, top_k)
            else:
                return self._hybrid_search(params, top_k)
        except Exception as e:
            logger.warning(f"Search failed, falling back to vector-only: {e}")
            try:
                return self._vector_search(params, top_k)
            except Exception as e2:
                logger.error(f"Vector search also failed: {e2}")
                return []

    def _build_filter(self, params: SearchParams) -> str | None:
        conditions = []
        if params.filter_page:
            escaped = params.filter_page.replace("'", "\\'")
            conditions.append(f"page = '{escaped}'")
        # Tag filtering: all requested tags must be in the tags array
        if params.filter_tags:
            for tag in params.filter_tags:
                escaped = tag.replace("'", "\\'")
                conditions.append(f"array_has(tags, '{escaped}')")
        return " AND ".join(conditions) if conditions else None

    def _vector_search(self, params: SearchParams, top_k: int) -> list[SearchResult]:
        q = self._table.search(params.query_vector).limit(top_k)
        where = self._build_filter(params)
        if where:
            q = q.where(where)
        rows = q.to_list()
        return [_row_to_result(r, r.get("_distance", 0.0)) for r in rows]

    def _keyword_search(self, params: SearchParams, top_k: int) -> list[SearchResult]:
        q = self._table.search(params.query_text, query_type="fts").limit(top_k)
        where = self._build_filter(params)
        if where:
            q = q.where(where)
        rows = q.to_list()
        return [_row_to_result(r, r.get("_score", 0.0)) for r in rows]

    def _hybrid_search(self, params: SearchParams, top_k: int) -> list[SearchResult]:
        from lancedb.rerankers import RRFReranker
        reranker = RRFReranker()
        q = (
            self._table.search(query_type="hybrid")
            .vector(params.query_vector)
            .text(params.query_text)
            .limit(top_k)
            .rerank(reranker)
        )
        where = self._build_filter(params)
        if where:
            q = q.where(where)
        rows = q.to_list()
        return [_row_to_result(r, r.get("_relevance_score", 0.0)) for r in rows]

    def get_stats(self) -> dict:
        try:
            total = self._table.count_rows()
            pages_result = self._table.search().select(["page"]).to_list()
            unique_pages = len({r["page"] for r in pages_result})
            return {"total_chunks": total, "total_pages": unique_pages}
        except Exception as e:
            logger.warning(f"Could not get stats: {e}")
            return {"total_chunks": 0, "total_pages": 0}

    def create_fts_index(self) -> None:
        try:
            self._table.create_fts_index("text", replace=True)
            self._table.create_fts_index("page", replace=True)
            logger.info("FTS index created on text and page fields")
        except Exception as e:
            logger.warning(f"Could not create FTS index: {e}")

    def close(self) -> None:
        pass  # lancedb connections don't require explicit close
