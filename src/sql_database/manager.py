import os, asyncio, json
import tempfile
import pymysql
import shutil
from pymysql import MySQLError
from pymysql.cursors import DictCursor
from src.sql_database.base import DBNotFoundError, DBOperationError
from src.sql_database.implementations.mysql import MySQLConnector
from src.sql_database.factory import DBConnectorBaseFactory
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat

from src.utils import logger


class SqlDataBaseManager:
    """数据库管理器

    统一管理多种类型的数据库实例，提供统一的外部接口
    """
    def __init__(self, work_dir: str):
        """
        初始化知识库管理器

        Args:
            work_dir: 工作目录
        """
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)

        # 知识库实例缓存 {kb_type: kb_instance}
        self.db_instances: dict[str, MySQLConnector] = {}

        # 全局数据库元信息 {db_id: metadata_with_kb_type}
        # self.global_databases_meta: dict[str, dict] = {}

        # self.db_name_to_id: dict[str, str] = {}

        # 元数据锁
        self._metadata_lock = asyncio.Lock()

        # 加载全局元数据
        # self._load_global_metadata()
        # self._normalize_global_metadata()

        # # 初始化已存在的知识库实例
        # self._initialize_existing_dbs()


    async def initialize(self):
        """异步初始化"""
        # 初始化已存在的知识库实例
        self._initialize_existing_dbs()
        logger.info("SqlDatabaseManager initialized")

    # def _update_db_name2id(self):
    #     for database_id, database_meta in self.global_databases_meta.items():
    #         database_name = database_meta.get("name")
    #         self.db_name_to_id[database_name] = database_id

    async def _load_all_metadata(self):
        """异步加载所有元数据 - 保留兼容性的空方法，现在由 KB 实例自行加载"""
        pass

    def _initialize_existing_dbs(self):
        """初始化已存在的知识库实例"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        async def _async_init():
            db_repo = SqlDatabaseRepository()
            rows = await db_repo.get_all()

            db_types_in_use = set()
            for row in rows:
                db_type = row.db_type or "mysql"
                db_types_in_use.add(db_type)

            logger.info(f"[InitializeKB] 发现 {len(db_types_in_use)} 种知识库类型: {db_types_in_use}")

            # 为每种使用中的知识库类型创建实例并加载元数据
            for db_type in db_types_in_use:
                try:
                    db_instance = self._get_or_create_db_instance(db_type)
                    # 让 KB 实例自行加载元数据
                    await db_instance._load_metadata()
                    logger.info(f"[InitializeKB] {db_type} 实例已初始化")
                except Exception as e:
                    logger.error(f"Failed to initialize {db_type} knowledge base: {e}")
                    import traceback

                    logger.error(traceback.format_exc())

        # 在事件循环中运行异步初始化
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_init())
        except RuntimeError:
            asyncio.run(_async_init())

    
    def _get_or_create_db_instance(self, db_type: str) -> MySQLConnector:
        """
        获取或创建知识库实例

        Args:
            kb_type: 知识库类型

        Returns:
            知识库实例
        """
        # self._update_db_name2id()
        if db_type in self.db_instances:
            return self.db_instances[db_type]

        # 创建新的知识库实例
        db_work_dir = os.path.join(self.work_dir, f"{db_type}_data")
        db_instance = DBConnectorBaseFactory.create(db_type, db_work_dir)

        self.db_instances[db_type] = db_instance
        logger.info(f"Created {db_type} knowledge base instance")
        return db_instance

    async def _get_db_for_database(self, db_id: str) -> MySQLConnector:
        """
        根据数据库ID获取对应的知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例

        Raises:
            KBNotFoundError: 数据库不存在或知识库类型不支持
        """
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        db = await db_repo.get_by_id(db_id)

        if db is None:
            raise DBNotFoundError(f"Database {db_id} not found")

        db_type = db.db_type or "lightrag"

        if not DBConnectorBaseFactory.is_type_supported(db_type):
            raise DBNotFoundError(f"Unsupported knowledge base type: {db_type}")

        return self._get_or_create_db_instance(db_type)

    def _get_db_for_database_sync(self, db_id: str) -> MySQLConnector:
        """同步版本的 _get_db_for_database，用于兼容同步调用"""
        try:
            loop = asyncio.get_running_loop()
            return loop.run_until_complete(self._get_db_for_database(db_id))
        except RuntimeError:
            return asyncio.run(self._get_db_for_database(db_id))

    # =============================================================================
    # 统一的外部接口 - 与原始 LightRagBasedKB 兼容
    # =============================================================================

    async def aget_kb(self, db_id: str) -> MySQLConnector:
        """异步获取知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例
        """
        return await self._get_db_for_database(db_id)

    def get_kb(self, db_id: str) -> MySQLConnector:
        """同步获取知识库实例（兼容性方法，用于同步上下文）

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例
        """
        return self._get_db_for_database_sync(db_id)

    def test_connection(self, config: dict) -> bool:
        try:
            connection = pymysql.connect(
                host=config["host"],
                user=config["user"],
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
            return connection

        except MySQLError as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise ConnectionError(f"MySQL connection failed: {e}")

    async def get_databases(self) -> dict:
        """获取所有数据库信息"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        rows = await db_repo.get_all()

        all_databases = []
        for row in rows:
            db_instance = self._get_or_create_db_instance(row.db_type or "mysql")
            db_info = db_instance.get_database_info(row.db_id)
            if db_info:
                # 补充 share_config 和 additional_params
                db_info["share_config"] = row.share_config or {"is_shared": True, "accessible_departments": []}
                # db_info["additional_params"] = row.additional_params or {}
                all_databases.append(db_info)
        return {"databases": all_databases}

    def get_database_instance(self, db_id: str) -> MySQLConnector:
        """Public accessor to fetch the underlying knowledge base instance by database id.

        This provides a simple compatibility layer for callers that expect a
        `get_kb` method on the manager.
        """
        return self._get_db_for_database(db_id)

    def _get_or_create_kb_instance(self, kb_type: str) -> MySQLConnector:
        """
        获取或创建知识库实例

        Args:
            kb_type: 知识库类型

        Returns:
            知识库实例
        """
        if kb_type in self.db_instances:
            return self.db_instances[kb_type]

        # 创建新的知识库实例
        kb_work_dir = os.path.join(self.work_dir, f"{kb_type}_data")
        kb_instance = DBConnectorBaseFactory.create(kb_type, kb_work_dir)

        self.db_instances[kb_type] = kb_instance
        logger.info(f"Created {kb_type} knowledge base instance")
        return kb_instance

    async def check_accessible(self, user: dict, db_id: str) -> bool:
        """检查用户是否有权限访问数据库

        Args:
            user: 用户信息字典
            db_id: 数据库ID

        Returns:
            bool: 是否有权限
        """
        # 超级管理员有权访问所有
        if user.get("role") == "superadmin":
            return True

        from src.repositories.sql_database_repository import SqlDatabaseRepository

        sdb_repo = SqlDatabaseRepository()
        sdb = await sdb_repo.get_by_id(db_id)
        if sdb is None:
            return False

        share_config = sdb.share_config or {}
        is_shared = share_config.get("is_shared", True)

        # 如果是全员共享，则有权限
        if is_shared:
            return True

        # 检查部门权限
        user_department_id = user.get("department_id")
        accessible_departments = share_config.get("accessible_departments", [])

        if user_department_id is None:
            return False

        # 转换为整数进行比较（前端可能传递字符串，后端存储为整数）
        try:
            user_department_id = int(user_department_id)
            accessible_departments = [int(d) for d in accessible_departments]
        except (ValueError, TypeError):
            return False

        return user_department_id in accessible_departments


    async def get_databases_by_user(self, user: dict) -> dict:
        """根据用户权限获取知识库列表

        Args:
            user: 用户信息字典，包含 role 和 department_id

        Returns:
            过滤后的知识库列表
        """
        all_databases = (await self.get_databases()).get("databases", [])

        # 超级管理员可以看到所有知识库
        if user.get("role") == "superadmin":
            return {"databases": all_databases}

        filtered_databases = []

        for db in all_databases:
            db_id = db.get("db_id")
            if not db_id:
                continue

            if await self.check_accessible(user, db_id):
                filtered_databases.append(db)

        return {"databases": filtered_databases}

    async def database_name_exists(self, database_name: str) -> bool:
        """检查知识库名称是否已存在"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        from src.storage.postgres.manager import pg_manager

        # 确保 pg_manager 已初始化
        if not pg_manager._initialized:
            pg_manager.initialize()

        sdb_repo = SqlDatabaseRepository()
        rows = await sdb_repo.get_all()
        for row in rows:
            if (row.name or "").lower() == database_name.lower():
                return True
        return False

    async def create_database(
        self, 
        database_name: str, 
        description: str, 
        db_type: str, 
        connect_info:dict, 
        share_config: dict | None = None,
        **kwargs
    ) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            kb_type: 知识库类型，默认为lightrag
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数，包括chunk_size和chunk_overlap

        Returns:
            数据库信息字典
        """
        if not DBConnectorBaseFactory.is_type_supported(db_type):
            available_types = list(DBConnectorBaseFactory.get_available_types().keys())
            raise ValueError(f"Unsupported knowledge base type: {db_type}. Available types: {available_types}")
        # 检查名称是否已存在
        if await self.database_name_exists(database_name):
            raise ValueError(f"数据库名称 '{database_name}' 已存在，请使用其他名称")

        # 默认共享配置
        if share_config is None:
            share_config = {"is_shared": True, "accessible_departments": []}

        db_instance = self._get_or_create_db_instance(db_type)
        db_info = await db_instance.create_database(database_name, description, connect_info=connect_info, **kwargs)
        db_id = db_info["db_id"]

        from src.repositories.sql_database_repository import SqlDatabaseRepository

        sdb_repo = SqlDatabaseRepository()
        updated = await sdb_repo.update(db_id, {"share_config": share_config})
        if updated is None:
            await sdb_repo.create(
                {
                    "db_id": db_id,
                    "name": database_name,
                    "description": description,
                    "db_type": db_type,
                    "connect_info": connect_info,
                    "share_config": share_config,
                }
            )

        logger.info(f"Created {db_type} database: {database_name} ({db_id}) with {kwargs}")
        db_info["share_config"] = share_config
        return db_info

    async def delete_database(self, db_id: str) -> dict:
        """删除数据库"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository
        try:
            db_instance = await self._get_db_for_database(db_id)
            result = db_instance.delete_database(db_id)

            # 删除数据库记录
            db_repo = SqlDatabaseRepository()
            await db_repo.delete(db_id)

            return result
        except DBNotFoundError as e:
            logger.warning(f"Database {db_id} not found during deletion: {e}")
            return {"message": "删除成功"}

    def get_connection(self, db_id: str):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.get_connection(db_id)

    def invalidate_connection(self, db_id: str):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.invalidate_connection(db_id)

    async def get_database_info(self, db_id: str) -> dict | None:
        """获取数据库详细信息"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        db = await db_repo.get_by_id(db_id)
        if db is None:
            return None

        try:
            db_instance = await self._get_db_for_database(db_id)
            if not len(db_instance.tables_meta):
                await self.initialize_tables(db_id)
                logger.debug(f"Initialize tables for {db_id}")
            db_info = db_instance.get_database_info(db_id)
        except DBNotFoundError:
            db_info = {
                "db_id": db_id,
                "name": db.name,
                "description": db.description,
                "connect_info": db.connect_info,
                "db_type": db.db_type,
                "tables": {},
                "selected_tables": {},
                "row_count": 0,
                "status": "已连接",
            }

        # 添加数据库中的附加字段
        db_info["share_config"] = db.share_config or {"is_shared": True, "accessible_departments": []}
        return db_info


    async def initialize_tables(self, db_id: str) -> dict | None:
        db_instance = await self._get_db_for_database(db_id)
        return await db_instance.initalize_table(db_id)


    async def select_tables(self, db_id: str, table_ids: list[dict]) -> list[dict]:
        """设置表信息"""
        db_instance = await self._get_db_for_database(db_id)
        return await db_instance.select_tables(db_id, table_ids)

    async def update_database(self, db_id:str, name:str, description:str, share_config:dict):
        from src.repositories.sql_database_repository import SqlDatabaseRepository

        db_instance = await self._get_db_for_database(db_id)
        db_instance.update_database(db_id, name, description, share_config)

        # 准备更新数据
        update_data: dict = {
            "name": name,
            "description": description,
        }
        if share_config is not None:
            update_data["share_config"] = share_config

        # 保存到数据库
        db_repo = SqlDatabaseRepository()
        await db_repo.update(db_id, update_data)

        return await self.get_database_info(db_id)

    
    async def unselect_table(self, db_id: str, table_id: str) -> dict:
        """取消设置表"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.unselect_table(table_id)

    async def get_table_basic_info(self, db_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_table_basic_info(db_id, file_id)

    async def get_tables(self, db_id: str) -> dict:
        """获取数据库表信息"""
        db_instance = await self._get_db_for_database(db_id)
        return await db_instance.get_tables()

    async def get_selected_tables(self, db_id: str) -> dict:
        """获取已选择的数据库表信息"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_selected_tables()

    async def get_table_info(self, db_id: str, table_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_table_info(db_id, table_id)

    def table_existed_in_db(self, db_id: str | None, table_name: str | None) -> bool:
        """检查指定数据库中是否存在相同内容哈希的文件"""
        if not db_id or not table_name:
            return False

        try:
            db_instance = self._get_db_for_database(db_id)
        except DBNotFoundError:
            return False

        for file_info in db_instance.tables_meta.values():
            if file_info.get("database_id") != db_id:
                continue
            if file_info.get("table_name") == table_name:
                return True

        return False


    def get_cursors(self) -> dict[str, dict]:
        """获取所有检索器"""
        all_cursors= {}

        # 收集所有知识库的检索器
        for db_instance in self.db_instances.values():
            cursors = db_instance.get_cursors()
            all_cursors.update(cursors)

        return all_cursors

    def get_cursor(self, db_id):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.get_cursor(db_id)