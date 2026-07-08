from __future__ import annotations

from typing import Any

from sqlalchemy import select, update as sa_update

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_sql_database import SqlDatabase


class SqlDatabaseRepository:
    async def get_all(self) -> list[SqlDatabase]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabase))
            return list(result.scalars().all())

    async def get_activated(self) -> list[SqlDatabase]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabase).where(SqlDatabase.is_activate == True))
            return list(result.scalars().all())

    async def deactivate_all_except(self, active_ids: list[str]) -> None:
        if not active_ids:
            return
        async with pg_manager.get_async_session_context() as session:
            stmt = sa_update(SqlDatabase).where(~SqlDatabase.db_id.in_(active_ids)).values(is_activate=False)
            await session.execute(stmt)

    async def get_by_id(self, db_id: str) -> SqlDatabase | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabase).where(SqlDatabase.db_id == db_id))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> SqlDatabase:
        kb = SqlDatabase(**data)
        async with pg_manager.get_async_session_context() as session:
            session.add(kb)
        return kb

    async def update(self, db_id: str, data: dict[str, Any]) -> SqlDatabase | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabase).where(SqlDatabase.db_id == db_id))
            kb = result.scalar_one_or_none()
            if kb is None:
                return None
            for key, value in data.items():
                setattr(kb, key, value)
        return kb

    async def delete(self, db_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabase).where(SqlDatabase.db_id == db_id))
            kb = result.scalar_one_or_none()
            if kb is not None:
                await session.delete(kb)
