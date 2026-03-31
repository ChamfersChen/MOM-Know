import os

from yuxi.storage.postgres.models_sql_examples import SqlExample, SqlExampleInfo
from yuxi.repositories.sql_example_repository import SqlExampleRepository
from yuxi import config
from yuxi.models.embed import OtherEmbedding



class SqlExampleService:
    def __init__(self):
        self.sql_example_repository = SqlExampleRepository()
        config_dict = config.embed_model_names['siliconflow/BAAI/bge-m3'].model_dump()
        config_dict["api_key"] = os.getenv(config_dict["api_key"]) or config_dict["api_key"]
        self.embedder = OtherEmbedding(
                model=config_dict.get("name"),
                base_url=config_dict.get("base_url"),
                api_key=config_dict.get("api_key"),
            )


    async def get_all_sql_examples(self) -> list[SqlExampleInfo]:
        all_sqls = await self.sql_example_repository.get_all()
        return [SqlExampleInfo(**sql.__dict__) for sql in all_sqls]

    async def get_sql_example_by_host_port(self, host: str, port: int) -> list[SqlExampleInfo]:
        all_sqls = await self.sql_example_repository.get_by_host_port(host=host, port=port)
        return [SqlExampleInfo(**sql.__dict__) for sql in all_sqls] 

    async def enable_sql_example(self, id:int, enabled: bool) -> SqlExampleInfo:
        sql = await self.sql_example_repository.enable(id, enabled)

        return SqlExampleInfo(**sql.__dict__)

    async def create_sql_example(self, sql_example: SqlExampleInfo) -> SqlExampleInfo:
        sql = sql_example.sql
        description = sql_example.description
        datasource_host = sql_example.datasource_host
        datasource_port = sql_example.datasource_port
        enabled = sql_example.enabled
        create_time = sql_example.create_time
        embedding = await self.embedder.aencode(description) # TODO : 需要根据术语名称生成embedding
        row = await self.sql_example_repository.create(
            {
                "sql":sql,
                "description":description,
                "embedding":embedding[0],
                "datasource_host":datasource_host,
                "datasource_port":datasource_port,
                "enabled":enabled,
                "create_time":create_time,
            }
        )

        return row

    async def update_sql_example(self, sql_example: SqlExampleInfo) -> SqlExampleInfo:
        """更新SQL示例

        Parameters
        ----------
        terminology : TerminologyInfo

        Returns
        -------
        list[TerminologyInfo]
        """
        id = sql_example.id
        sql = sql_example.sql
        description = sql_example.description
        datasource_host = sql_example.datasource_host
        datasource_port = sql_example.datasource_port
        enabled = sql_example.enabled
        embedding = await self.embedder.aencode(description) # TODO : 需要根据术语名称生成embedding
        row = await self.sql_example_repository.update(
            {
                "id":id,
                "sql":sql,
                "description":description,
                "embedding":embedding[0],
                "datasource_host":datasource_host,
                "datasource_port":datasource_port,
                "enabled":enabled,
            }
        )

        return row


    async def get_with_query(self, query: str, ds_host: str, ds_port: int) -> list[SqlExample]:
        embedding = await self.embedder.aencode(query)
        return await self.sql_example_repository.get_with_embedding(embedding[0], ds_host, ds_port)


    async def delete_by_id(self, id: int) -> None:
        return await self.sql_example_repository.delete(id)