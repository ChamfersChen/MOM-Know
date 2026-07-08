from yuxi.sql_database.vector_store import SqlExampleVectorStore
from yuxi.storage.postgres.models_sql_examples import SqlExample, SqlExampleInfo
from yuxi.repositories.sql_example_repository import SqlExampleRepository
from yuxi.utils import logger


class SqlExampleService:
    def __init__(self, vector_store: SqlExampleVectorStore | None = None):
        self.sql_example_repository = SqlExampleRepository()
        self.vector_store = vector_store

    async def get_all_sql_examples(self) -> list[SqlExampleInfo]:
        all_sqls = await self.sql_example_repository.get_all()
        return [SqlExampleInfo(**sql.__dict__) for sql in all_sqls]

    async def get_sql_example_by_host_port(self, host: str, port: int) -> list[SqlExampleInfo]:
        all_sqls = await self.sql_example_repository.get_by_host_port(host=host, port=port)
        return [SqlExampleInfo(**sql.__dict__) for sql in all_sqls]

    async def enable_sql_example(self, id: int, enabled: bool) -> SqlExampleInfo:
        sql = await self.sql_example_repository.enable(id, enabled)
        ret = SqlExampleInfo(**sql.__dict__)

        if self.vector_store is not None:
            try:
                await self.vector_store.index_sql(
                    row_id=sql.id,
                    sql=sql.sql or "",
                    description=sql.description or "",
                    datasource_host=sql.datasource_host,
                    datasource_port=sql.datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to sync SQL example {sql.id} enable status to Milvus: {exc}")

        return ret

    async def create_sql_example(self, sql_example: SqlExampleInfo) -> SqlExampleInfo:
        sql = sql_example.sql
        description = sql_example.description
        datasource_host = sql_example.datasource_host
        datasource_port = sql_example.datasource_port
        enabled = sql_example.enabled
        create_time = sql_example.create_time
        row = await self.sql_example_repository.create(
            {
                "sql": sql,
                "description": description,
                "datasource_host": datasource_host,
                "datasource_port": datasource_port,
                "enabled": enabled,
                "create_time": create_time,
            }
        )

        if self.vector_store is not None:
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize SQL example vector store: {exc}")
            try:
                await self.vector_store.index_sql(
                    row_id=row.id,
                    sql=sql or "",
                    description=description or "",
                    datasource_host=datasource_host,
                    datasource_port=datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to index SQL example {row.id} to Milvus: {exc}")

        return row

    async def update_sql_example(self, sql_example: SqlExampleInfo) -> SqlExampleInfo:
        id = sql_example.id
        sql = sql_example.sql
        description = sql_example.description
        datasource_host = sql_example.datasource_host
        datasource_port = sql_example.datasource_port
        enabled = sql_example.enabled
        row = await self.sql_example_repository.update(
            {
                "id": id,
                "sql": sql,
                "description": description,
                "datasource_host": datasource_host,
                "datasource_port": datasource_port,
                "enabled": enabled,
            }
        )

        if self.vector_store is not None:
            try:
                await self.vector_store.remove_sql(id)
            except Exception as exc:
                logger.warning(f"Failed to remove old SQL example {id} from Milvus: {exc}")
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize SQL example vector store: {exc}")
            try:
                await self.vector_store.index_sql(
                    row_id=id,
                    sql=sql or "",
                    description=description or "",
                    datasource_host=datasource_host,
                    datasource_port=datasource_port,
                    enabled=enabled,
                )
            except Exception as exc:
                logger.warning(f"Failed to re-index SQL example {id} to Milvus: {exc}")

        return row

    async def get_with_query(self, query: str, ds_host: str | None = None, ds_port: int | None = None) -> list[dict]:
        if self.vector_store is not None:
            try:
                await self.vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize SQL example vector store: {exc}")
            try:
                return await self.vector_store.search(
                    query=query,
                    top_k=10,
                    datasource_host=ds_host,
                    datasource_port=ds_port,
                )
            except Exception as exc:
                logger.warning(f"Failed to search SQL examples from Milvus, falling back to pgvector: {exc}")

        from yuxi.models.embed import select_embedding_model
        from yuxi.config import config

        model = select_embedding_model(config.embed_model)
        embedding = await model.aencode([query])
        if ds_host and ds_port is not None:
            return await self.sql_example_repository.get_with_embedding(embedding[0], ds_host, ds_port)
        return []

    async def delete_by_id(self, id: int) -> None:
        await self.sql_example_repository.delete(id)
        if self.vector_store is not None:
            try:
                await self.vector_store.remove_sql(id)
            except Exception as exc:
                logger.warning(f"Failed to remove SQL example {id} from Milvus: {exc}")
