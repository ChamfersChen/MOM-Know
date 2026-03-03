from __future__ import annotations

from typing import Any

from sqlalchemy import select, text

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_terminology import Terminology

embedding_sql = f"""
SELECT id, pid, word, similarity
FROM
(SELECT id, pid, word, specific_ds, enabled,
( 1 - (embedding <=> :embedding_array) ) AS similarity
FROM terminology AS child
) TEMP
WHERE similarity > 0.5 AND enabled = true
AND (specific_ds = false OR specific_ds IS NULL)
ORDER BY similarity DESC
LIMIT 10;
"""

class TerminologyRepository:
    async def get_all(self) -> list[Terminology]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology))
            return list(result.scalars().all())

    async def get_by_id(self, pid: str) -> Terminology | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology).where(Terminology.id == pid))
            return result.scalar_one_or_none()

    async def get_by_host_port(self, host: str, port:int) -> Terminology | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology).where(Terminology.datasource_host==host, 
                                                                     Terminology.datasource_port==port))
            return result.scalar_one_or_none()

    async def check_exists(self, word: str, host: str, port: int) -> Terminology | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology).where(Terminology.word == word, 
                                                                     Terminology.datasource_host == host,
                                                                     Terminology.datasource_port == port))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> Terminology:
        term = Terminology(**data)
        # 判断word是否已经存在
        if await self.check_exists(term.word, term.datasource_host, term.datasource_port):
            raise Exception("word already exists")

        async with pg_manager.get_async_session_context() as session:
            session.add(term)
        return term

    async def update(self, data: dict[str, Any]) -> Terminology | None:
        term = Terminology(**data)
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology).where(Terminology.id == term.id))
            term = result.scalar_one_or_none()

            if term is None:
                return None
            
            for key, value in data.items():
                setattr(term, key, value)
        return term

    async def delete(self, id: int) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Terminology).where(Terminology.id == id))
            term = result.scalar_one_or_none()
            if term is not None:
                await session.delete(term)
            
            children = await session.execute(select(Terminology).where(Terminology.pid == id))
            for child in children.scalars().all():
                await session.delete(child)

    async def get_terms_with_embedding(self, embedding) -> list[dict[str, Any]]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(text(embedding_sql),
                            {'embedding_array': str(embedding)})
            
            return result.mappings().all()
