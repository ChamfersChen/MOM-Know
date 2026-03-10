from __future__ import annotations

from typing import Any

from sqlalchemy import select, text

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_sql_examples import SqlExample

embedding_sql = f"""
SELECT id, sql, similarity, description
FROM
(SELECT id, sql, datasource_host, datasource_port, enabled, description, 
( 1 - (embedding <=> :embedding_array) ) AS similarity
FROM sql_examples AS child
) TEMP
WHERE similarity > 0.1 AND enabled = true
AND datasource_host = :ds_host and datasource_port = :ds_port
ORDER BY similarity DESC
LIMIT 10;
"""

class SqlExampleRepository:
    async def get_all(self) -> list[SqlExample]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample))
            return list(result.scalars().all())

    async def get_by_id(self, id: int) -> SqlExample | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.id == id))
            return result.scalar_one_or_none()

    async def get_children_by_pid(self, pid: int) -> list[SqlExample]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.pid == pid))
            return list(result.scalars().all())


    async def get_by_host_port(self, host: str, port:int) -> list[SqlExample]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.datasource_host==host, 
                                                                     SqlExample.datasource_port==port))
            return list(result.scalars().all())

    async def check_exists(self, sql: str, host: str, port: int) -> SqlExample | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.sql == sql, 
                                                                     SqlExample.datasource_host == host,
                                                                     SqlExample.datasource_port == port))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> SqlExample:
        sql = SqlExample(**data)
        # 判断sql是否已经存在
        if await self.check_exists(sql.sql, sql.datasource_host, sql.datasource_port):
            raise Exception("sql already exists")

        async with pg_manager.get_async_session_context() as session:
            session.add(sql)
        return sql

    async def update(self, data: dict[str, Any]) -> SqlExample | None:
        term = SqlExample(**data)
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.id == term.id))
            term = result.scalar_one_or_none()

            if term is None:
                return None
            
            for key, value in data.items():
                setattr(term, key, value)
        return term

    async def enable(self, id:int, enable:bool) -> SqlExample | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.id == id))
            term = result.scalar_one_or_none()
            if term is None:
                return None
            setattr(term, "enabled", enable)
        return term

    async def delete(self, id: int) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlExample).where(SqlExample.id == id))
            sql = result.scalar_one_or_none()
            if sql is not None:
                await session.delete(sql)
            
    async def delete_by_pid(self, pid: int) -> None:
        async with pg_manager.get_async_session_context() as session:
            children = await session.execute(select(SqlExample).where(SqlExample.pid == pid))
            for child in children.scalars().all():
                await session.delete(child)

    async def get_with_embedding(self, embedding, ds_host: str, ds_port: int) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(text(embedding_sql),
                            {
                                'embedding_array': str(embedding),
                                'ds_host': str(ds_host),
                                'ds_port': ds_port,
                            })
            
            return result.mappings().all()
