import os
import threading
import time
import asyncio
from contextlib import contextmanager
from typing import Any
from src.sql_database.base import ConnectorBase
import pymysql
from pymysql import MySQLError
from pymysql.cursors import DictCursor
from src.utils import logger, hashstr
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat


class MySQLConnector(ConnectorBase):
    """MySQL 数据库连接器"""

    def __init__(self, work_dir:str, **kwargs):
        super().__init__(work_dir)
        self.host = kwargs.get("host", os.getenv("MYSQL_HOST") or "")
        self.user = kwargs.get("user", os.getenv("MYSQL_USER") or "")
        self.password = kwargs.get("password", os.getenv("MYSQL_PASSWORD") or "")
        self.port = kwargs.get("port", os.getenv("MYSQL_PORT") or "")
        self.database = kwargs.get("database", os.getenv("MYSQL_DATABASE") or "")

        # 存储集合映射
        self.connections: dict[str, pymysql.Connection] = {}


        self._lock = threading.Lock()
        self.last_connection_time = 0
        self.max_connection_age = 3600  # 1小时后重新连接
        self._metadata_lock = asyncio.Lock()


    def _flush_connection(self):
        current_time = time.time()
        db_ids = list(self.connections.keys())
        with self._lock:
            for db_id in db_ids:
                if not self.connections[db_id].open or current_time - self.last_connection_time > self.max_connection_age:
                    self.connections[db_id].close()
                    del self.connections[db_id]

    def _get_connection(self, db_id) -> pymysql.Connection:
        """获取数据库连接"""
        if db_id not in self.connections:
            return self._create_connection(db_id)
        
        return self.connections[db_id]

    def prepare_table_name_metadata(self, db_id: str, table_name) -> dict:
        """
        准备文件或URL的元数据
        """
        table_id = f"table_{hashstr(str(table_name) + str(time.time()), 6)}"

        return {
            "database_id": db_id,
            "table_id": table_id,
            'is_choose': False
        }

    async def initalize_table(self, db_id):

        db_name = self.databases_meta[db_id]['connect_info']['database']
        with self.get_cursor(db_id) as cursor:
            # 获取表名
            sql = f"SELECT TABLE_NAME AS table_name, TABLE_COMMENT AS table_comment FROM  information_schema.tables WHERE table_schema = '{db_name}';"
            cursor.execute(sql)
            # logger.debug("Executed `SHOW TABLES` query")
            tables = cursor.fetchall()

            if not tables:
                return "数据库中没有找到任何表"
            for table in tables:
                table_name = table['table_name']
                table_comment = table['table_comment']
                metadata = self.prepare_table_name_metadata(db_id, table_name)
                metadata['tablename'] = table_name
                metadata['description'] = table_comment

                table_record = metadata.copy()
                self.tables_meta[table_name] = table_record

            await self._save_metadata()

    def update_database(self, db_id: str, name: str, description: str, share_config:dict=None) -> dict:
        """
        更新数据库

        Args:
            db_id: 数据库ID
            name: 新名称
            description: 新描述

        Returns:
            更新后的数据库信息
        """
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description

        # 如果提供了 llm_info，则更新（仅针对 LightRAG 类型）
        if share_config is not None:
            self.databases_meta[db_id]["share_config"] = share_config

        asyncio.create_task(self._save_metadata())

        return self.get_database_info(db_id)


    def _create_connection(self, db_id) -> pymysql.Connection:
        """创建新的数据库连接"""
        max_retries = 3
        config = self.databases_meta[db_id]['connect_info']
        for attempt in range(max_retries):
            try:
                connection = pymysql.connect(
                    host=config["host"],
                    user=config["username"],
                    password=config["password"],
                    database=config["database"],
                    port=config["port"],
                    charset=config.get("charset", "utf8mb4"),
                    cursorclass=DictCursor,
                    connect_timeout=10,
                    read_timeout=60,  # 增加读取超时
                    write_timeout=30,
                    autocommit=True,  # 自动提交
                )
                logger.info(f"MySQL connection established successfully (attempt {attempt + 1})")
                # self.connections[db_id] = connection
                return connection

            except MySQLError as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # 指数退避
                else:
                    logger.error(f"Failed to connect to MySQL after {max_retries} attempts: {e}")
                    raise ConnectionError(f"MySQL connection failed: {e}")

    # def test_connection(self) -> bool:
    #     """测试连接是否有效"""
    #     try:
    #         if self.connection and self.connection.open:
    #             # 执行简单查询测试连接
    #             with self.connection.cursor() as cursor:
    #                 cursor.execute("SELECT 1")
    #                 cursor.fetchone()
    #             return True
    #     except Exception as _:
    #         pass
    #     return False

    def _invalidate_connection(self, db_id = None):
        """关闭并清理失效的连接"""
        try:
            if db_id:
                self.connections[db_id].close()
        except Exception:
            pass
        finally:
            del self.connections[db_id]

    @contextmanager
    def get_cursor(self, db_id):
        """获取数据库游标的上下文管理器"""
        max_retries = 2
        cursor = None
        connection = None
        last_error: Exception | None = None

        # 优先确保成功获取游标再交给调用方执行查询
        for attempt in range(max_retries):
            try:
                connection = self._get_connection(db_id)
                cursor = connection.cursor()
                break
            except Exception as e:
                last_error = e
                logger.warning(f"Failed to acquire cursor (attempt {attempt + 1}): {e}")
                self._invalidate_connection(db_id)
                cursor = None
                connection = None
                if attempt == max_retries - 1:
                    raise e
                time.sleep(1)

        if cursor is None or connection is None:
            raise last_error or ConnectionError("Unable to acquire MySQL cursor")

        try:
            yield cursor
            connection.commit()
        except Exception as e:
            try:
                connection.rollback()
            except Exception:
                pass

            # 标记连接失效，等待下一次获取时重建
            if "MySQL" in str(e) or "connection" in str(e).lower():
                logger.warning(f"MySQL connection error encountered, invalidating connection: {e}")
                self._invalidate_connection(db_id)

            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass

    def get_cursors(self):
        cursors = {}
        for db_id, meta in self.databases_meta.items():
            cursors[db_id] = {
                "db_name": meta["connection_info"]['database'],
                "description": meta["description"],
                "cursor": self.get_cursor(db_id),
                "metadata": meta,
            }
        return cursors

        
    def close(self):
        """关闭数据库连接"""
        for db_id, connection in self.connections.items():
            if connection:
                connection.close()
                self.connections[db_id] = None
                logger.info("MySQL connection closed")

    def get_connection(self, db_id) -> pymysql.Connection:
        """对外暴露的连接获取方法"""
        return self._get_connection(db_id)

    def invalidate_connection(self, db_id):
        """手动标记连接失效"""
        self._invalidate_connection(db_id)

    # @property
    # def database_name(self) -> str:
    #     """返回当前配置的数据库名称"""
    #     return self.config["database"]
    

    @property
    def db_type(self) -> str:
        """数据库类型标识"""
        return "mysql"
    
    async def select_tables(self, db_id: str, table_ids: list[str]) -> list[dict]:
        """设置指定db的表"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        
        # 删除db_id的表
        del_table_ids = []
        for table_id in self.selected_tables_meta.keys():
            if self.selected_tables_meta[table_id]['database_id'] == db_id:
                del_table_ids.append(table_id)
        for did in del_table_ids:
            del self.selected_tables_meta[did]

        processed_items_info = []
        for table_id in table_ids:
            
            # table_name = table['table_name']
            assert table_id in self.tables_meta.keys(), "Table not found"

            metadata = self.tables_meta[table_id]
            table_record = metadata.copy()
            # del table_record["table_id"]
            self.selected_tables_meta[table_id] = table_record
            table_record["table_id"] = table_id
            processed_items_info.append(table_record)
        
        async with self._metadata_lock:
            self._save_metadata()

        return processed_items_info

    async def unselect_table(self, table_id: str) -> None:
        """取消选择数据库表"""
        ret = {}
        # 使用锁确保元数据操作的原子性
        async with self._metadata_lock:
            if table_id in self.selected_tables_meta:
                ret = self.selected_tables_meta[table_id]
                del self.selected_tables_meta[table_id]
                self._save_metadata()
        return ret


    async def get_tables(self) -> dict:
        """获取数据库表信息"""
        return {"meta": self.tables_meta}

    async def get_selected_tables(self) -> dict:
        """获取已选择的数据库表信息"""
        return {"meta": self.selected_tables_meta}

    async def get_tables(self) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        # 合并基本信息和内容信息
        return {"meta": self.tables_meta}


    async def get_table_info(self, table_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        if table_id not in self.tables_meta:
            raise Exception(f"File not found: {table_id}")

        # 合并基本信息和内容信息
        basic_info = await self.get_table_basic_info(table_id)
        return {**basic_info}

    async def get_table_basic_info(self, table_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        if table_id not in self.tables_meta:
            raise Exception(f"File not found: {table_id}")

        return {"meta": self.tables_meta[table_id]}
    
    async def delete_database(self, db_id: str) -> dict:
        """
        删除数据库

        Args:
            db_id: 数据库ID

        Returns:
            操作结果
        """
        if db_id in self.databases_meta:
            self.get_connection(db_id).close()

            from src.repositories.sql_database_repository import SqlDatabaseRepository

            # 删除相关文件记录
            tables_to_delete = [fid for fid, finfo in self.tables_meta.items() if finfo.get("database_id") == db_id]
            for table_id in tables_to_delete:
                del self.tables_meta[table_id]

            # 删除数据库记录
            del self.databases_meta[db_id]
            await SqlDatabaseRepository().delete(db_id)
            await self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            import shutil

            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}