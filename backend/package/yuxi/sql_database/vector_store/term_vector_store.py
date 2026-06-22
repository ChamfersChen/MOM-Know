import asyncio
import json
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

TERM_COLLECTION = "terminology"
TERM_CONTENT_FIELD = "content"
VECTOR_METRIC_TYPE = "COSINE"
CONTENT_ANALYZER_PARAMS = {"type": "chinese"}


class TermVectorStore:
    """术语表的向量存储管理。

    在 Milvus 中创建 `terminology` 集合，支持语义/关键词/混合检索。
    """

    def __init__(self):
        self.connection_alias = f"term_milvus_{hashstr(TERM_COLLECTION, 6)}"
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
                logger.warning(f"TermVectorStore: database operation failed, using default: {exc}")
            self._connected = True
            logger.info(f"TermVectorStore connected to Milvus at {uri}")
        except Exception as exc:
            logger.error(f"TermVectorStore failed to connect to Milvus: {exc}")
            raise

    def _create_collection(self, embedding_dim: int):
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
            FieldSchema(name="word", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="other_words", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(
                name=TERM_CONTENT_FIELD,
                dtype=DataType.VARCHAR,
                max_length=65535,
                enable_analyzer=True,
                analyzer_params=CONTENT_ANALYZER_PARAMS,
            ),
            FieldSchema(name="specific_ds", dtype=DataType.BOOL),
            FieldSchema(name="datasource_host", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="datasource_port", dtype=DataType.INT64),
            FieldSchema(name="enabled", dtype=DataType.BOOL),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            FieldSchema(name="content_sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
        ]
        bm25_function = Function(
            name="term_content_bm25",
            input_field_names=[TERM_CONTENT_FIELD],
            output_field_names=["content_sparse"],
            function_type=FunctionType.BM25,
        )
        schema = CollectionSchema(
            fields=fields,
            description="Terminology for SQL database semantic search",
            functions=[bm25_function],
        )
        collection = Collection(name=TERM_COLLECTION, schema=schema, using=self.connection_alias)
        index_params = {"metric_type": VECTOR_METRIC_TYPE, "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
        collection.create_index("embedding", index_params)
        sparse_index_params = {
            "metric_type": "BM25",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"inverted_index_algo": "DAAT_MAXSCORE"},
        }
        collection.create_index("content_sparse", sparse_index_params)
        logger.info(f"Created Milvus collection {TERM_COLLECTION} with dim={embedding_dim}")
        return collection

    def _get_or_create_collection(self, embedding_dim: int) -> Collection:
        self._connect()
        if utility.has_collection(TERM_COLLECTION, using=self.connection_alias):
            collection = Collection(name=TERM_COLLECTION, using=self.connection_alias)
            fields = {f.name: f for f in collection.schema.fields}
            dim_field = fields.get("embedding")
            has_enabled = "enabled" in fields
            if dim_field is not None and dim_field.params.get("dim") == embedding_dim and has_enabled:
                logger.info(f"Reusing existing Milvus collection {TERM_COLLECTION}")
                return collection
            logger.warning(
                f"Schema changed (dim_match={dim_field is not None and dim_field.params.get('dim') == embedding_dim}, "
                f"has_enabled={has_enabled}), dropping and recreating {TERM_COLLECTION}"
            )
            utility.drop_collection(TERM_COLLECTION, using=self.connection_alias)
        return self._create_collection(embedding_dim)

    async def clear_all(self):
        """删除并重建 terminology 集合，清空所有数据。"""
        try:
            self._connect()
            if utility.has_collection(TERM_COLLECTION, using=self.connection_alias):
                self.collection = None
                await asyncio.to_thread(utility.drop_collection, TERM_COLLECTION, using=self.connection_alias)
            await self.initialize_collection()
            logger.info("Cleared and recreated terminology collection")
        except Exception as exc:
            logger.warning(f"Failed to clear terminology collection: {exc}")

    async def initialize_collection(self, embedding_model_spec: str | None = None):
        if embedding_model_spec is None:
            from yuxi.config import config

            embedding_model_spec = config.embed_model
        model_info = model_cache.get_model_info(embedding_model_spec)
        if not model_info or model_info.model_type != "embedding":
            raise ValueError(f"Invalid embedding model: {embedding_model_spec}")
        embedding_dim = model_info.dimension or 1024
        self.collection = await asyncio.to_thread(self._get_or_create_collection, embedding_dim)
        await asyncio.to_thread(self.collection.load)
        return self.collection

    def _get_embedding_function(self, embedding_model_spec: str):
        from yuxi.models.embed import select_embedding_model

        model = select_embedding_model(embedding_model_spec)
        batch_size = int(getattr(model, "batch_size", 40) or 40)
        return partial(model.abatch_encode, batch_size=batch_size)

    def _build_content(self, word: str, description: str, other_words: list[str]) -> str:
        parts = [word]
        if description:
            parts.append(description)
        if other_words:
            parts.extend(other_words)
        return " ".join(parts)

    async def index_term(
        self,
        term_id: int,
        word: str,
        description: str,
        other_words: list[str],
        specific_ds: bool,
        datasource_host: str,
        datasource_port: int,
        enabled: bool,
        embedding_model_spec: str | None = None,
    ):
        if self.collection is None:
            await self.initialize_collection(embedding_model_spec)
        if embedding_model_spec is None:
            from yuxi.config import config

            embedding_model_spec = config.embed_model
        embed_fn = self._get_embedding_function(embedding_model_spec)
        content = self._build_content(word, description, other_words)
        embeddings = await embed_fn([content])
        entity = [
            [str(term_id)],
            [word],
            [description or ""],
            [json.dumps(other_words, ensure_ascii=False)],
            [content],
            [specific_ds],
            [datasource_host],
            [datasource_port],
            [enabled],
            embeddings,
        ]
        self.collection.insert(entity)
        logger.info(f"Indexed term {term_id} ('{word}') into Milvus")

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

        contents = []
        for e in entries:
            word = e.get("word", "")
            description = e.get("description", "")
            other_words = e.get("other_words", [])
            content = self._build_content(word, description, other_words)
            contents.append(content)

        embeddings = await embed_fn(contents)

        ids = [str(e.get("id", "")) for e in entries]
        words = [e.get("word", "") for e in entries]
        descriptions = [e.get("description") or "" for e in entries]
        other_words_all = [json.dumps(e.get("other_words", []), ensure_ascii=False) for e in entries]
        specific_ds_all = [e.get("specific_ds", False) for e in entries]
        datasource_hosts = [e.get("datasource_host", "") for e in entries]
        datasource_ports = [int(e.get("datasource_port", 0)) for e in entries]
        enabled_all = [e.get("enabled", True) for e in entries]

        entity = [
            ids,
            words,
            descriptions,
            other_words_all,
            contents,
            specific_ds_all,
            datasource_hosts,
            datasource_ports,
            enabled_all,
            embeddings,
        ]
        res = self.collection.insert(entity)
        logger.info(f"Batch indexed {res.insert_count}/{len(entries)} terms into Milvus")

    async def remove_term(self, term_id: int):
        if self.collection is None:
            return
        self.collection.delete(f'id == "{term_id}"')

    async def search(
        self,
        query: str,
        top_k: int = 10,
        search_mode: str = "hybrid",
        datasource_host: str | None = None,
        datasource_port: int | None = None,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        bm25_drop_ratio_search: float = 0.0,
    ) -> list[dict]:
        if self.collection is None:
            return []

        self.collection.load()
        expr = "enabled == True"
        if datasource_host and datasource_port is not None:
            expr += f' and datasource_host == "{datasource_host}" and datasource_port == {datasource_port}'
        elif datasource_host:
            expr += f' and datasource_host == "{datasource_host}"'

        search_mode = str(search_mode or "hybrid").lower()
        if search_mode not in {"vector", "keyword", "hybrid"}:
            search_mode = "hybrid"

        output_fields = [
            "id",
            "word",
            "description",
            "other_words",
            "specific_ds",
            "datasource_host",
            "datasource_port",
            "enabled",
        ]
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
                anns_field="content_sparse",
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
            anns_field="content_sparse",
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
                    "id": entity.get("id"),
                    "word": entity.get("word"),
                    "description": entity.get("description"),
                    "other_words": json.loads(entity.get("other_words") or "[]"),
                    "specific_ds": entity.get("specific_ds"),
                    "datasource_host": entity.get("datasource_host"),
                    "datasource_port": entity.get("datasource_port"),
                    "enabled": entity.get("enabled"),
                    "score": float(hit.distance or 0.0),
                }
            )
        return results
