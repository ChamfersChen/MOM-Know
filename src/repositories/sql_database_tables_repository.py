from __future__ import annotations

from typing import Any

from sqlalchemy import select

from src.utils.datetime_utils import utc_now_naive
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_sql_database import SqlDatabaseTable


class SqlDatabaseTableRepository:
    async def get_all(self) -> list[SqlDatabaseTable]:
        """获取所有文件记录"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable))
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> SqlDatabaseTable:
        table = SqlDatabaseTable(**data)
        async with pg_manager.get_async_session_context() as session:
            session.add(table)
        return table

    async def update(self, table_id: str, data: dict[str, Any]) -> SqlDatabaseTable | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.table_id == table_id))
            table = result.scalar_one_or_none()
            if table is None:
                return None
            for key, value in data.items():
                if key in ['updated_at', 'created_at']:
                    value = utc_now_naive()
                setattr(table, key, value)
        return table
    async def get_by_table_id(self, table_id: str) -> SqlDatabaseTable | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.table_id == table_id))
            return result.scalar_one_or_none()

    async def get_by_table_name(self, tableanme: str) -> SqlDatabaseTable | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.tablename == tableanme))
            return result.scalar_one_or_none()

    async def list_by_db_id(self, db_id: str) -> list[SqlDatabaseTable]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.database_id == db_id))
            return list(result.scalars().all())

    async def upsert(self, table_id: str, data: dict[str, Any]) -> SqlDatabaseTable:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.table_id == table_id))
            existing = result.scalar_one_or_none()
            if existing is None:
                record = SqlDatabaseTable(table_id=table_id, **data)
                session.add(record)
                return record
            for key, value in data.items():
                setattr(existing, key, value)
            return existing

    async def delete(self, table_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.table_id == table_id))
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    async def delete_by_db_id(self, db_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(SqlDatabaseTable).where(SqlDatabaseTable.database_id == db_id))
            for record in result.scalars().all():
                await session.delete(record)
