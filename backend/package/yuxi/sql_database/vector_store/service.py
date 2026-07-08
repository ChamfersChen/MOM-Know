from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any

from pymilvus import (
    AnnSearchRequest,
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    Function,
    FunctionType,
    WeightedRanker,
    connections,
    db,
    utility,
)

from yuxi.models.providers.cache import model_cache
from yuxi.utils import hashstr, logger

SQL_TABLES_COLLECTION = "sql_tables"
CONTENT_FIELD = "content"
CONTENT_SPARSE_FIELD = "content_sparse"
VECTOR_METRIC_TYPE = "COSINE"
CONTENT_ANALYZER_PARAMS = {"type": "chinese"}


class SqlTableVectorStore:
    """SQL 数据库表的向量存储管理。

    为所有 sql_database 下的表提供一个共享的 Milvus 集合，
    通过 db_id 字段区分不同数据库。
    """

    def __init__(self):
        self.connection_alias = f"sql_milvus_{hashstr(SQL_TABLES_COLLECTION, 6)}"
        self.collection: Collection | None = None
        self._connected = False

    def _connect(self):
        if self._connected:
            return
        uri = os.getenv("MILVUS_URI", "http://localhost:19530")
        token = os.getenv("MILVUS_TOKEN", "")
        milvus_db = os.getenv("MILVUS_DB_NAME", "yuxi")
        try:
            connections.connect(alias=self.connection_alias, uri=uri, token=token)
            try:
                if milvus_db not in db.list_database(using=self.connection_alias):
                    db.create_database(milvus_db, using=self.connection_alias)
                db.using_database(milvus_db, using=self.connection_alias)
            except Exception as exc:
                logger.warning(f"SqlTableVectorStore: database operation failed, using default: {exc}")
            self._connected = True
            logger.info(f"SqlTableVectorStore connected to Milvus at {uri}")
        except Exception as exc:
            logger.error(f"SqlTableVectorStore failed to connect to Milvus: {exc}")
            raise

    def _create_collection(self, embedding_dim: int):
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
            FieldSchema(
                name=CONTENT_FIELD,
                dtype=DataType.VARCHAR,
                max_length=65535,
                enable_analyzer=True,
                analyzer_params=CONTENT_ANALYZER_PARAMS,
            ),
            FieldSchema(name="table_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="table_name", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="db_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="db_name", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="is_choose", dtype=DataType.BOOL),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            FieldSchema(name=CONTENT_SPARSE_FIELD, dtype=DataType.SPARSE_FLOAT_VECTOR),
        ]
        bm25_function = Function(
            name="content_bm25",
            input_field_names=[CONTENT_FIELD],
            output_field_names=[CONTENT_SPARSE_FIELD],
            function_type=FunctionType.BM25,
        )
        schema = CollectionSchema(
            fields=fields,
            description="SQL database table descriptions for semantic search",
            functions=[bm25_function],
        )
        collection = Collection(name=SQL_TABLES_COLLECTION, schema=schema, using=self.connection_alias)
        index_params = {"metric_type": VECTOR_METRIC_TYPE, "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
        collection.create_index("embedding", index_params)
        sparse_index_params = {
            "metric_type": "BM25",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"inverted_index_algo": "DAAT_MAXSCORE"},
        }
        collection.create_index(CONTENT_SPARSE_FIELD, sparse_index_params)
        logger.info(f"Created Milvus collection {SQL_TABLES_COLLECTION} with dim={embedding_dim}")
        return collection

    def _get_or_create_collection(self, embedding_dim: int) -> Collection:
        self._connect()
        if utility.has_collection(SQL_TABLES_COLLECTION, using=self.connection_alias):
            collection = Collection(name=SQL_TABLES_COLLECTION, using=self.connection_alias)
            fields = {f.name: f for f in collection.schema.fields}
            dim_field = fields.get("embedding")
            has_is_choose = "is_choose" in fields
            if dim_field is not None and dim_field.params.get("dim") == embedding_dim and has_is_choose:
                logger.info(f"Reusing existing Milvus collection {SQL_TABLES_COLLECTION}")
                return collection
            logger.warning(
                f"Schema changed (dim_match={dim_field is not None and dim_field.params.get('dim') == embedding_dim}, has_is_choose={has_is_choose}), dropping and recreating {SQL_TABLES_COLLECTION}"
            )
            utility.drop_collection(SQL_TABLES_COLLECTION, using=self.connection_alias)
        return self._create_collection(embedding_dim)

    async def clear_all(self):
        """删除并重建 sql_tables 集合，清空所有数据。"""
        try:
            self._connect()
            if utility.has_collection(SQL_TABLES_COLLECTION, using=self.connection_alias):
                self.collection = None
                await asyncio.to_thread(utility.drop_collection, SQL_TABLES_COLLECTION, using=self.connection_alias)
            await self.initialize_collection()
            logger.info("Cleared and recreated sql_tables collection")
        except Exception as exc:
            logger.warning(f"Failed to clear sql_tables collection: {exc}")

    async def initialize_collection(self, embedding_model_spec: str | None = None):
        if embedding_model_spec is None:
            from yuxi.config import config

            embedding_model_spec = config.embed_model
        model_info = model_cache.get_model_info(embedding_model_spec)
        if not model_info or model_info.model_type != "embedding":
            raise ValueError(f"无效的 embedding 模型: {embedding_model_spec}")
        embedding_dim = model_info.dimension or 1024
        self.collection = await asyncio.to_thread(self._get_or_create_collection, embedding_dim)
        await asyncio.to_thread(self.collection.load)
        return self.collection

    def _get_embedding_function(self, embedding_model_spec: str):
        from yuxi.models.embed import select_embedding_model

        model = select_embedding_model(embedding_model_spec)
        batch_size = int(getattr(model, "batch_size", 40) or 40)
        return partial(model.abatch_encode, batch_size=batch_size)

    async def index_table_record(
        self,
        table_id: str,
        table_name: str,
        db_id: str,
        db_name: str,
        content: str,
        is_choose: bool = False,
        embedding_model_spec: str | None = None,
    ):
        if self.collection is None:
            await self.initialize_collection(embedding_model_spec)
        if embedding_model_spec is None:
            from yuxi.config import config

            embedding_model_spec = config.embed_model
        embed_fn = self._get_embedding_function(embedding_model_spec)
        embeddings = await embed_fn([content])
        row_id = table_id
        entity = [
            [row_id],
            [content],
            [table_id],
            [table_name],
            [db_id],
            [db_name],
            [is_choose],
            embeddings,
        ]

        def _insert():
            self.collection.insert(entity)

        await asyncio.to_thread(_insert)
        logger.info(f"Indexed table {table_name} ({table_id}) into Milvus")

    async def batch_index(
        self,
        entries: list[dict[str, Any]],
        embedding_model_spec: str | None = None,
    ):
        if not entries:
            return
        if self.collection is None:
            await self.initialize_collection(embedding_model_spec)
        if embedding_model_spec is None:
            from yuxi.config import config

            embedding_model_spec = config.embed_model
        embed_fn = self._get_embedding_function(embedding_model_spec)
        texts = [e["content"] for e in entries]
        embeddings = await embed_fn(texts)
        row_ids = [e["table_id"] for e in entries]
        table_ids = [e["table_id"] for e in entries]
        table_names = [e["table_name"] for e in entries]
        db_ids = [e["db_id"] for e in entries]
        db_names = [e["db_name"] for e in entries]
        is_chooses = [e.get("is_choose", False) for e in entries]
        entity = [row_ids, texts, table_ids, table_names, db_ids, db_names, is_chooses, embeddings]

        res = self.collection.insert(entity)
        # def _insert():
        #     self.collection.insert(entity)

        # await asyncio.to_thread(_insert)
        logger.info(f"Batch indexed {res.insert_count}/{len(entries)} tables into Milvus")

    async def remove_table(self, table_id: str):
        if self.collection is None:
            return

        self.collection.delete(f'table_id == "{table_id}"')
        # def _delete():
        #     self.collection.delete(f'table_id == "{table_id}"')

        # await asyncio.to_thread(_delete)

    async def remove_by_db_id(self, db_id: str):
        if self.collection is None:
            return

        def _delete():
            self.collection.delete(f'db_id == "{db_id}"')

        await asyncio.to_thread(_delete)

    async def search(
        self,
        query: str,
        db_ids: list[str] | None = None,
        top_k: int = 10,
        search_mode: str = "hybrid",
        is_choose_only: bool = False,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        bm25_drop_ratio_search: float = 0.0,
    ) -> list[dict]:
        if self.collection is None:
            return []

        self.collection.load()
        expr = self._build_search_expr(db_ids, is_choose_only=is_choose_only)
        search_mode = str(search_mode or "hybrid").lower()
        if search_mode not in {"vector", "keyword", "hybrid"}:
            search_mode = "hybrid"

        output_fields = ["content", "table_id", "table_name", "db_id", "db_name", "is_choose"]
        results: list[dict] = []

        if search_mode == "vector":
            results = await self._vector_search(query, expr, top_k, output_fields)
        elif search_mode == "keyword":
            results = await self._keyword_search(query, expr, top_k, output_fields)
        else:
            results = await self._hybrid_search(
                query,
                expr,
                top_k,
                output_fields,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
                bm25_drop_ratio_search=bm25_drop_ratio_search,
            )

        return results

    def _build_search_expr(self, db_ids: list[str] | None = None, is_choose_only: bool = False) -> str | None:
        parts = []
        if db_ids:
            escaped = [d.replace('"', '\\"') for d in db_ids]
            if len(escaped) == 1:
                parts.append(f'db_id == "{escaped[0]}"')
            else:
                joined = '", "'.join(escaped)
                parts.append(f'db_id in ["{joined}"]')
        if is_choose_only:
            parts.append("is_choose == True")
        return " and ".join(parts) if parts else None

    async def _vector_search(self, query: str, expr: str | None, top_k: int, output_fields: list[str]) -> list[dict]:
        from yuxi.config import config

        embedding_model_spec = config.embed_model
        embed_fn = self._get_embedding_function(embedding_model_spec)

        query_embedding = await embed_fn([query])
        search_params = {"metric_type": VECTOR_METRIC_TYPE, "params": {"nprobe": 10}}

        def _search():
            return self.collection.search(
                data=query_embedding,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=output_fields,
            )

        raw = await asyncio.to_thread(_search)
        return self._hits_to_results(raw)

    async def _keyword_search(self, query: str, expr: str | None, top_k: int, output_fields: list[str]) -> list[dict]:
        bm25_search_params = {"metric_type": "BM25", "params": {"drop_ratio_search": 0.0}}

        def _search():
            return self.collection.search(
                data=[query],
                anns_field=CONTENT_SPARSE_FIELD,
                param=bm25_search_params,
                limit=top_k,
                expr=expr,
                output_fields=output_fields,
            )

        raw = await asyncio.to_thread(_search)
        return self._hits_to_results(raw)

    async def _hybrid_search(
        self,
        query: str,
        expr: str | None,
        top_k: int,
        output_fields: list[str],
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        bm25_drop_ratio_search: float = 0.0,
    ) -> list[dict]:
        from yuxi.config import config

        embedding_model_spec = config.embed_model
        embed_fn = self._get_embedding_function(embedding_model_spec)

        query_embedding = await embed_fn([query])
        vector_request = AnnSearchRequest(
            data=query_embedding,
            anns_field="embedding",
            param={"metric_type": VECTOR_METRIC_TYPE, "params": {"nprobe": 10}},
            limit=top_k,
            expr=expr,
        )
        bm25_request = AnnSearchRequest(
            data=[query],
            anns_field=CONTENT_SPARSE_FIELD,
            param={"metric_type": "BM25", "params": {"drop_ratio_search": bm25_drop_ratio_search}},
            limit=top_k,
            expr=expr,
        )

        def _search():
            return self.collection.hybrid_search(
                reqs=[vector_request, bm25_request],
                rerank=WeightedRanker(vector_weight, bm25_weight),
                limit=top_k,
                output_fields=output_fields,
            )

        raw = await asyncio.to_thread(_search)
        return self._hits_to_results(raw)

    def _hits_to_results(self, raw) -> list[dict]:
        if not raw or len(raw) == 0 or len(raw[0]) == 0:
            return []
        results = []
        for hit in raw[0]:
            entity = hit.entity
            results.append(
                {
                    "table_id": entity.get("table_id"),
                    "table_name": entity.get("table_name"),
                    "db_id": entity.get("db_id"),
                    "db_name": entity.get("db_name"),
                    "is_choose": entity.get("is_choose"),
                    "content": entity.get("content"),
                    "score": float(hit.distance or 0.0),
                }
            )
        return results
