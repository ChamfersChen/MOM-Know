import asyncio
import os

import pymysql
from pymysql import MySQLError
from pymysql.cursors import DictCursor

from yuxi.sql_database.base import ConnectorBase, DBNotFoundError
from yuxi.sql_database.factory import DBConnectorBaseFactory
from yuxi.sql_database.graphs import SqlDBGraphService
from yuxi.sql_database.vector_store import SqlExampleVectorStore, SqlTableVectorStore, TermVectorStore
from yuxi.utils import logger
from yuxi.utils.sql_password_crypto import sql_password_crypto


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
        self.db_instances: dict[str, ConnectorBase] = {}

        # 知识库名称与ID映射, 用于Tool调用时使用
        self.db_name_to_id: dict[str, str] = {}
        self.db_host_port_name_to_id: dict[str, str] = {}

        # 向量存储（由外部注入）
        self.vector_store: SqlTableVectorStore = None
        # 术语向量存储（由外部注入）
        self.term_vector_store: TermVectorStore = None
        # SQL 示例向量存储（由外部注入）
        self.sql_example_vector_store: SqlExampleVectorStore = None
        # 图谱服务（由外部注入）
        self.graph_service: SqlDBGraphService = None

        # 当前激活的数据库 ID 列表（由 reupload 设置，供工具调用时默认使用）
        self.active_db_ids: list[str] = []

    async def initialize(self):
        """异步初始化：加载所有 DB 元数据 → 清空 Milvus + Neo4j → 索引激活库。"""
        await self._load_all_db_metadata()

        # 清空 Milvus（表/术语/SQL 示例）和 Neo4j 中所有旧数据
        await self.clear_all_sql_data()

        # 仅索引 is_activate=True 的数据库到向量存储
        await self.batch_reindex_all(self.active_db_ids)

        # 术语表和 SQL 示例表按激活库的 host:port 筛选索引
        await self._sync_terms_and_sqls()

        logger.info(f"SqlDatabaseManager initialized, active_db_ids={self.active_db_ids}")

    async def _load_all_db_metadata(self):
        """遍历所有数据库，加载元数据并填充名称映射。"""
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        rows = await db_repo.get_all()

        db_types_in_use = set()
        self.active_db_ids = []
        for row in rows:
            db_type = row.db_type or "mysql"
            db_types_in_use.add(db_type)
            self.db_name_to_id[str(row.name)] = row.db_id
            if row.is_activate:
                self.active_db_ids.append(row.db_id)

            host = row.connect_info["host"]
            port = row.connect_info["port"]
            self.db_host_port_name_to_id[f"{host}:{port}/{row.name}"] = str(row.db_id)

        logger.info(f"[InitializeDB] 发现 {len(db_types_in_use)} 种数据库类型: {db_types_in_use}")

        for db_type in db_types_in_use:
            try:
                db_instance = self._get_or_create_db_instance(db_type)
                await db_instance._load_metadata()
                logger.info(f"[InitializeDB] {db_type} 实例已初始化")
            except Exception as e:
                logger.error(f"Failed to initialize {db_type} knowledge base: {e}")
                import traceback

                logger.error(traceback.format_exc())

    async def _load_all_metadata(self):
        """保留兼容性的空方法。"""
        pass

    def _get_or_create_db_instance(self, db_type: str) -> ConnectorBase:
        """
        获取或创建知识库实例

        Args:
            kb_type: 知识库类型

        Returns:
            知识库实例
        """
        if db_type in self.db_instances:
            return self.db_instances[db_type]

        # 创建新的数据库实例
        db_work_dir = os.path.join(self.work_dir, f"{db_type}_data")
        db_instance = DBConnectorBaseFactory.create(db_type, db_work_dir)

        self.db_instances[db_type] = db_instance
        logger.info(f"Created {db_type} knowledge base instance")
        return db_instance

    async def _get_db_for_database(self, db_id: str) -> ConnectorBase:
        """
        根据数据库ID获取对应的知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例

        Raises:
            KBNotFoundError: 数据库不存在或知识库类型不支持
        """
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        db = await db_repo.get_by_id(db_id)

        if db is None:
            raise DBNotFoundError(f"Database {db_id} not found")

        db_type = db.db_type or "mysql"

        if not DBConnectorBaseFactory.is_type_supported(db_type):
            raise DBNotFoundError(f"Unsupported knowledge base type: {db_type}")

        return self._get_or_create_db_instance(db_type)

    def _get_db_for_database_sync(self, db_id: str) -> ConnectorBase:
        """同步版本的 _get_db_for_database，用于兼容同步调用"""
        try:
            loop = asyncio.get_running_loop()
            return loop.run_until_complete(self._get_db_for_database(db_id))
        except RuntimeError:
            return asyncio.run(self._get_db_for_database(db_id))

    # =============================================================================
    # 统一的外部接口 - 与原始 LightRagBasedKB 兼容
    # =============================================================================

    async def aget_kb(self, db_id: str) -> ConnectorBase:
        """异步获取知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例
        """
        return await self._get_db_for_database(db_id)

    def get_kb(self, db_id: str) -> ConnectorBase:
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
                user=config["username"],
                password=config["password"],
                database=config["database"],
                port=int(config["port"]),
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
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        # get all databases from database
        db_repo = SqlDatabaseRepository()
        rows = await db_repo.get_all()

        all_databases = []
        for row in rows:
            db_instance = self._get_or_create_db_instance(row.db_type or "mysql")
            db_info = db_instance.get_database_info(row.db_id)
            if db_info:
                db_info["connect_info"] = sql_password_crypto.sanitize_connect_info_for_output(
                    db_info.get("connect_info")
                )
                # 补充 share_config
                db_info["share_config"] = row.share_config or {"is_shared": True, "accessible_departments": []}
                all_databases.append(db_info)
        return {"databases": all_databases}

    def get_database_instance(self, db_id: str) -> ConnectorBase:
        """Public accessor to fetch the underlying knowledge base instance by database id.

        This provides a simple compatibility layer for callers that expect a
        `get_kb` method on the manager.
        """
        return self._get_db_for_database(db_id)

    def _get_or_create_kb_instance(self, kb_type: str) -> ConnectorBase:
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

        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

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
            assert db_id, "数据库ID不能为空"
            self.db_name_to_id[db["name"]] = db_id

            port = db["connect_info"]["port"]
            host = db["connect_info"]["host"]
            self.db_host_port_name_to_id[f"{host}:{port}/{db['name']}"] = db_id
            if not db_id:
                continue

            if await self.check_accessible(user, db_id):
                filtered_databases.append(db)

        return {"databases": filtered_databases}

    async def database_name_exists(self, database_name: str) -> bool:
        """检查知识库名称是否已存在"""
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository
        from yuxi.storage.postgres.manager import pg_manager

        # 确保 pg_manager 已初始化
        if not pg_manager._initialized:
            pg_manager.initialize()

        sdb_repo = SqlDatabaseRepository()
        rows = await sdb_repo.get_all()
        for row in rows:
            if (row.name or "").lower() == database_name.lower():
                return True
        return False

    async def database_ip_port_name_exists(self, connect_info: dict) -> bool:
        """检查知识库名称是否已存在"""
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository
        from yuxi.storage.postgres.manager import pg_manager

        # 确保 pg_manager 已初始化
        if not pg_manager._initialized:
            pg_manager.initialize()

        sdb_repo = SqlDatabaseRepository()
        rows = await sdb_repo.get_all()
        for row in rows:
            if (
                (row.connect_info.get("database") or "").lower() == str(connect_info.get("database", "")).lower()
                and (row.connect_info.get("host") or "").lower() == str(connect_info.get("host", "")).lower()
                and str(row.connect_info.get("port", "")).lower() == str(connect_info.get("port", "")).lower()
            ):
                return True
        return False

    async def create_database(
        self,
        database_name: str,
        description: str,
        db_type: str,
        connect_info: dict,
        share_config: dict | None = None,
        related_db_ids: str | None = None,
        **kwargs,
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
        # if await self.database_name_exists(database_name):
        if await self.database_ip_port_name_exists(connect_info):
            raise ValueError(f"数据库名称 '{database_name}' 已存在，请使用其他名称")

        # 默认共享配置
        if share_config is None:
            share_config = {"is_shared": True, "accessible_departments": []}

        db_instance = self._get_or_create_db_instance(db_type)
        db_info = await db_instance.create_database(
            database_name,
            description,
            connect_info=connect_info,
            share_config=share_config,
            related_db_ids=related_db_ids,
            **kwargs,
        )
        db_id = db_info["db_id"]

        created_databases = set([v["database_id"] for v in db_instance.tables_meta.values()])
        if not created_databases or db_id not in created_databases:
            await self.initialize_tables(db_id)
            logger.debug(f"Initialize tables for {db_id}")

        db_info["connect_info"] = sql_password_crypto.sanitize_connect_info_for_output(db_info.get("connect_info"))
        return db_info

    async def delete_database(self, db_id: str) -> dict:
        """删除数据库"""
        try:
            db_instance = await self._get_db_for_database(db_id)
            db_info = db_instance.get_database_info(db_id)
            db_name = db_info["name"]
            db_host = db_info["connect_info"]["host"]
            db_port = db_info["connect_info"]["port"]

            # 清理向量存储
            if self.vector_store is not None:
                try:
                    await self.vector_store.remove_by_db_id(db_id)
                except Exception as exc:
                    logger.warning(f"清理向量存储失败 (db_id={db_id}): {exc}")

            # 清理图谱
            if self.graph_service is not None:
                try:
                    await asyncio.to_thread(self.graph_service.remove_graph, db_id)
                except Exception as exc:
                    logger.warning(f"清理图谱失败 (db_id={db_id}): {exc}")

            result = await db_instance.delete_database(db_id)
            # 删除数据库名称与 ID 的映射
            if db_name in self.db_name_to_id:
                del self.db_name_to_id[db_name]
            if f"{db_host}:{db_port}/{db_name}" in self.db_host_port_name_to_id:
                del self.db_host_port_name_to_id[f"{db_host}:{db_port}/{db_name}"]

            return result
        except DBNotFoundError as e:
            logger.warning(f"Database {db_id} not found during deletion: {e}")
            return {"message": "删除成功"}

    async def get_connection(self, db_id: str):
        db_instance = await self._get_db_for_database(db_id)
        return db_instance.get_connection(db_id)

    async def invalidate_connection(self, db_id: str):
        db_instance = await self._get_db_for_database(db_id)
        return db_instance.invalidate_connection(db_id)

    async def get_database_info(self, db_id: str) -> dict | None:
        """获取数据库详细信息"""
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        db_repo = SqlDatabaseRepository()
        db = await db_repo.get_by_id(db_id)
        if db is None:
            return None

        try:
            db_instance = await self._get_db_for_database(db_id)
            db_info = db_instance.get_database_info(db_id)
            db_info["connect_info"] = sql_password_crypto.sanitize_connect_info_for_output(db_info.get("connect_info"))
        except DBNotFoundError:
            db_info = {
                "db_id": db_id,
                "name": db.name,
                "description": db.description,
                "connect_info": sql_password_crypto.sanitize_connect_info_for_output(db.connect_info),
                "db_type": db.db_type,
                "tables": {},
                "related_db_ids": [],
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

    async def update_database(
        self,
        db_id: str,
        name: str,
        description: str,
        share_config: dict = None,
        related_db_ids: str | list[str] | None = None,
    ) -> dict:
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        db_instance = await self._get_db_for_database(db_id)
        old_info = db_instance.get_database_info(db_id)
        assert old_info, f"数据库信息为空. db_id: {db_id}"
        old_name = old_info["name"]

        db_instance.update_database(db_id, name, description, share_config, related_db_ids)

        db_info = db_instance.get_database_info(db_id)

        # 清理旧名称映射
        if old_name in self.db_name_to_id:
            del self.db_name_to_id[old_name]
        host_port = f"{old_info['connect_info']['host']}:{old_info['connect_info']['port']}"
        old_key = f"{host_port}/{old_name}"
        if old_key in self.db_host_port_name_to_id:
            del self.db_host_port_name_to_id[old_key]

        # 更新名称映射
        self.db_name_to_id[name] = db_id
        new_key = f"{host_port}/{name}"
        self.db_host_port_name_to_id[new_key] = db_id

        # 持久化到 PostgreSQL
        update_data: dict = {"name": name, "description": description}
        if share_config is not None:
            update_data["share_config"] = share_config
        if related_db_ids is not None:
            parsed_ids = related_db_ids.split(";") if isinstance(related_db_ids, str) else list(related_db_ids)
            update_data["related_db_ids"] = ";".join(parsed_ids)
        await SqlDatabaseRepository().update(db_id, update_data)

        # 名称变更时重索引所有表向量
        if name != old_name:
            await self.reindex_tables(db_id)

        # 更新图谱依赖关系
        if related_db_ids is not None and self.graph_service is not None:
            parsed_ids = related_db_ids.split(";") if isinstance(related_db_ids, str) else list(related_db_ids)
            await asyncio.to_thread(self.graph_service.remove_dependency, db_id)
            await asyncio.to_thread(self.graph_service.sync_dependencies, db_id, parsed_ids)

        return await self.get_database_info(db_id)

    async def update_tables(self, db_id: str, table_info: dict):
        db_instance = await self._get_db_for_database(db_id)
        db_instance.update_tables(db_id, table_info)
        # 重新同步向量存储和图谱
        # await self._sync_vector_store(db_id)
        # await self._sync_graph(db_id)
        return await self.get_database_info(db_id)

    async def get_tables(self, db_id: str) -> dict:
        """获取数据库表信息"""
        db_instance = await self._get_db_for_database(db_id)
        return await db_instance.get_tables()

    async def _sync_vector_store(self, db_id: str):
        """将指定数据库的所有表同步到向量存储"""
        if self.vector_store is None:
            return
        db_instance = await self._get_db_for_database(db_id)
        db_info = db_instance.get_database_info(db_id)
        if not db_info:
            return
        db_name = db_info.get("name", "")
        entries = []
        for tid, tinfo in db_instance.tables_meta.items():
            if tinfo.get("database_id") != db_id:
                continue
            if not tinfo.get("is_choose"):
                continue
            total_desc = tinfo.get("description") or ""
            if not total_desc:
                continue
            total_desc += tinfo.get("tablename") or ""
            db_desc = db_info.get("description") or ""
            total_desc += f"\t `{db_name}`数据库描述：{db_desc}" if db_desc else ""
            entries.append(
                {
                    "table_id": tid,
                    "table_name": tinfo.get("tablename", ""),
                    "db_id": db_id,
                    "db_name": db_name,
                    "is_choose": True,
                    "content": total_desc,
                }
            )
        if entries:
            await self.vector_store.batch_index(entries)

    async def _sync_graph(self, db_id: str):
        """将指定数据库的所有表同步到 Neo4j 图谱"""
        if self.graph_service is None:
            return
        db_instance = await self._get_db_for_database(db_id)
        db_info = db_instance.get_database_info(db_id)
        if not db_info:
            return
        db_name = db_info.get("name", "")
        description = db_info.get("description", "")
        tables = [
            tinfo
            for tinfo in db_instance.tables_meta.values()
            if tinfo.get("database_id") == db_id and tinfo.get("is_choose")
        ]
        await asyncio.to_thread(self.graph_service.sync_graph, db_id, db_name, description, tables)
        related = db_info.get("related_db_ids") or []
        await asyncio.to_thread(self.graph_service.sync_dependencies, db_id, related)

    async def search_tables(
        self,
        query: str,
        db_ids: list[str] | None = None,
        top_k: int = 10,
        search_mode: str = "hybrid",
        is_choose_only: bool = False,
        similarity_threshold: float = 0.0,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        bm25_drop_ratio_search: float = 0.0,
        reranker_model: str | None = None,
        use_graph_retrieval: bool = False,
        graph_weight: float = 0.5,
        search_terms: bool = False,
        search_sqls: bool = False,
    ) -> dict:
        """使用向量检索 + 可选重排 + 图谱检索搜索数据库表，并可联动检索术语和 SQL 示例。

        Args:
            query: 自然语言查询
            db_ids: 限制搜索的数据库 ID 列表，None 表示搜索全部
            top_k: 最终返回结果数
            search_mode: 检索模式 (vector/keyword/hybrid)
            is_choose_only: 仅检索 is_choose=True 的记录
            similarity_threshold: 分数过滤阈值，低于此值的结果被丢弃
            vector_weight: 向量检索权重 (hybrid 模式)
            bm25_weight: BM25 权重 (hybrid 模式)
            bm25_drop_ratio_search: BM25 降采样比例
            reranker_model: 重排序模型 spec，提供则启用重排
            use_graph_retrieval: 启用 Neo4j 图谱检索
            graph_weight: 图谱检索融合权重
            search_terms: 是否同时检索相关术语
            search_sqls: 是否同时检索相关 SQL 示例

        Returns:
            {"tables": [...], "terms": [...], "sqls": [...]}
        """
        logger.info(f"Activate db_ids: {self.active_db_ids}")
        if db_ids is None and self.active_db_ids:
            db_ids = self.active_db_ids

        result: dict = {"tables": [], "terms": [], "sqls": []}
        if self.vector_store is not None:
            recall_top_k = top_k
            if reranker_model or similarity_threshold > 0 or use_graph_retrieval:
                recall_top_k = max(top_k * 3, 50)

            tables = await self.vector_store.search(
                query=query,
                db_ids=db_ids,
                top_k=recall_top_k,
                search_mode=search_mode,
                is_choose_only=is_choose_only,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
                bm25_drop_ratio_search=bm25_drop_ratio_search,
            )

            if tables:
                if use_graph_retrieval and self.graph_service is not None:
                    try:
                        seed_weights = self._build_db_seed_weights(tables, decay=0.8)
                        if seed_weights:
                            seed_db_ids = list(seed_weights.keys())
                            graph_tables = await asyncio.to_thread(
                                self.graph_service.fetch_tables_by_db_cluster,
                                seed_db_ids,
                            )
                            if graph_tables:
                                for gt in graph_tables:
                                    gt["score"] = seed_weights.get(gt.get("db_id", ""), 0.0)
                                tables = self._fuse_rankings(tables, graph_tables, graph_weight)
                    except Exception as exc:
                        logger.warning(f"Graph retrieval failed, using vector results only: {exc}")

                if similarity_threshold > 0:
                    tables = [r for r in tables if (r.get("score") or 0.0) >= similarity_threshold]

                if reranker_model:
                    try:
                        from yuxi.models.rerank import get_reranker

                        reranker = get_reranker(reranker_model)
                        try:
                            documents = [r["content"] for r in tables]
                            scores = await reranker.acompute_score([query, documents], normalize=True)
                            for r, s in zip(tables, scores):
                                r["rerank_score"] = float(s)
                            tables.sort(key=lambda x: x.get("rerank_score", x.get("score", 0.0)), reverse=True)
                        finally:
                            await reranker.aclose()
                    except Exception as exc:
                        logger.warning(f"Reranking failed, falling back to vector scores: {exc}")

            result["tables"] = tables[:top_k]

        host_ports = await self._resolve_unique_host_ports(db_ids)

        if search_terms and self.term_vector_store is not None:
            try:
                await self.term_vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize term vector store: {exc}")
            try:
                if host_ports:
                    term_results = []
                    for host, port in host_ports:
                        terms = await self.term_vector_store.search(
                            query=query,
                            datasource_host=host,
                            datasource_port=port,
                        )
                        term_results.extend(terms)
                    result["terms"] = term_results
                else:
                    result["terms"] = await self.term_vector_store.search(query=query)
            except Exception as exc:
                logger.warning(f"Term search failed: {exc}")

        if search_sqls and self.sql_example_vector_store is not None:
            try:
                await self.sql_example_vector_store.initialize_collection()
            except Exception as exc:
                logger.warning(f"Failed to initialize SQL example vector store: {exc}")
            try:
                if host_ports:
                    sql_results = []
                    for host, port in host_ports:
                        sqls = await self.sql_example_vector_store.search(
                            query=query,
                            datasource_host=host,
                            datasource_port=port,
                        )
                        sql_results.extend(sqls)
                    result["sqls"] = sql_results
                else:
                    result["sqls"] = await self.sql_example_vector_store.search(query=query)
            except Exception as exc:
                logger.warning(f"SQL example search failed: {exc}")

        return result

    async def _resolve_unique_host_ports(
        self,
        db_ids: list[str] | None,
    ) -> list[tuple[str, int]]:
        """根据 db_id 列表从 PostgreSQL 解析唯一 (host, port) 对。"""
        if not db_ids:
            return []
        from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

        repo = SqlDatabaseRepository()
        seen = set()
        pairs: list[tuple[str, int]] = []
        for db_id in db_ids:
            try:
                db = await repo.get_by_id(db_id)
                if db is None:
                    continue
                info = db.connect_info or {}
                host = info.get("host")
                port = info.get("port")
                if host and port is not None:
                    key = (host, int(port))
                    if key not in seen:
                        seen.add(key)
                        pairs.append(key)
            except Exception as exc:
                logger.warning(f"Failed to resolve host/port for db_id={db_id}: {exc}")
        return pairs

    @staticmethod
    def _build_db_seed_weights(
        results: list[dict],
        decay: float = 0.8,
    ) -> dict[str, float]:
        """以 Milvus 检索结果的向量得分为种子，按 db_id 聚合、归一化为数据库权重。

        参照知识库 _build_graph_seed_weights 的模式：
        每个检索命中的表贡献其 score 到所属 db_id，累计后归一化。
        """
        raw: dict[str, float] = {}
        for r in results:
            db_id = r.get("db_id")
            if db_id:
                raw[db_id] = raw.get(db_id, 0.0) + (r.get("score") or 0.0)
        total = sum(raw.values())
        if total <= 0:
            return {}
        return {db_id: weight / total * decay for db_id, weight in raw.items()}

    @staticmethod
    def _fuse_rankings(
        base_tables: list[dict],
        graph_tables: list[dict],
        graph_weight: float,
    ) -> list[dict]:
        """RRF 融合向量检索与图谱检索的结果。"""
        fused: dict[str, dict] = {}
        rrf_k = 60.0

        def merge(table: dict, rank: int, weight: float, source: str) -> None:
            tid = table.get("table_id")
            if not tid:
                return
            score = weight / (rrf_k + rank)
            existing = fused.get(tid)
            if existing is None:
                existing = {**table, "fusion_score": 0.0, "fusion_sources": []}
                fused[tid] = existing
            existing["fusion_score"] += score
            existing["score"] = existing["fusion_score"]
            existing["fusion_sources"].append(source)
            if source == "graph" and "graph_score" in table:
                existing["graph_score"] = table["graph_score"]

        for rank, t in enumerate(base_tables, start=1):
            merge(t, rank, 1.0, "vector")
        for rank, t in enumerate(graph_tables, start=1):
            merge(t, rank, max(graph_weight, 0.0), "graph")

        return sorted(fused.values(), key=lambda x: x.get("fusion_score", 0.0), reverse=True)

    async def reindex_tables(self, db_id: str):
        """重建指定数据库所有表的向量索引"""
        if self.vector_store is None:
            return
        await self.vector_store.remove_by_db_id(db_id)
        await self._sync_vector_store(db_id)

    async def reindex_graph(self, db_id: str):
        """重建指定数据库的 Neo4j 图谱"""
        if self.graph_service is None:
            return
        await asyncio.to_thread(self.graph_service.remove_graph, db_id)
        await self._sync_graph(db_id)

    async def reindex_all(self, db_id: str):
        """重建指定数据库的所有索引（Milvus + Neo4j）"""
        await self.reindex_tables(db_id)
        await self.reindex_graph(db_id)

    async def batch_reindex_all(self, db_ids: list[str]):
        """批量重建多个数据库的所有索引（Milvus + Neo4j），一次写入避免逐库覆盖。"""
        # 1. Milvus: 收集全部 db_ids 的表数据，一次 batch_index
        if self.vector_store is not None and db_ids:
            all_entries = []
            for db_id in db_ids:
                db_instance = await self._get_db_for_database(db_id)
                db_info = db_instance.get_database_info(db_id)
                if not db_info:
                    continue
                db_name = db_info.get("name", "")
                for tid, tinfo in db_instance.tables_meta.items():
                    if tinfo.get("database_id") != db_id:
                        continue
                    if not tinfo.get("is_choose"):
                        continue
                    total_desc = tinfo.get("description") or ""
                    if not total_desc:
                        continue
                    all_entries.append(
                        {
                            "table_id": tid,
                            "table_name": tinfo.get("tablename", ""),
                            "db_id": db_id,
                            "db_name": db_name,
                            "is_choose": True,
                            "content": total_desc,
                        }
                    )
            if all_entries:
                await self.vector_store.batch_index(all_entries)
                logger.info(f"batch_reindex_all: indexed {len(all_entries)} tables from {len(db_ids)} databases")

        # 2. Neo4j: 先创建所有 Database / Table 节点，再统一处理依赖关系
        if self.graph_service is not None and db_ids:
            for db_id in db_ids:
                db_instance = await self._get_db_for_database(db_id)
                db_info = db_instance.get_database_info(db_id)
                if not db_info:
                    continue
                db_name = db_info.get("name", "")
                description = db_info.get("description", "")
                tables = [
                    tinfo
                    for tinfo in db_instance.tables_meta.values()
                    if tinfo.get("database_id") == db_id and tinfo.get("is_choose")
                ]
                await asyncio.to_thread(self.graph_service.sync_graph, db_id, db_name, description, tables)

            for db_id in db_ids:
                db_instance = await self._get_db_for_database(db_id)
                db_info = db_instance.get_database_info(db_id)
                if not db_info:
                    continue
                related = db_info.get("related_db_ids") or []
                if related:
                    await asyncio.to_thread(self.graph_service.sync_dependencies, db_id, related)
            logger.info(f"batch_reindex_all: synced {len(db_ids)} databases to Neo4j")

    def set_active_db_ids(self, db_ids: list[str] | None):
        """设置当前激活的数据库 ID 列表，供 search_tables 默认使用。"""
        self.active_db_ids = db_ids

    async def clear_all_sql_data(self):
        """清空 Milvus（三个集合）和 Neo4j 中所有与 sql 相关的数据。"""
        if self.vector_store is not None:
            await self.vector_store.clear_all()
        if self.term_vector_store is not None:
            await self.term_vector_store.clear_all()
        if self.sql_example_vector_store is not None:
            await self.sql_example_vector_store.clear_all()
        if self.graph_service is not None:
            await asyncio.to_thread(self.graph_service.clear_all)
        logger.info("All SQL data cleared from Milvus and Neo4j")

    async def _sync_terms_and_sqls(self):
        """根据激活数据库的 host:port，索引术语和 SQL 示例到 Milvus。"""
        host_ports = await self._resolve_unique_host_ports(self.active_db_ids)
        if not host_ports:
            return

        from yuxi.repositories.sql_example_repository import SqlExampleRepository
        from yuxi.repositories.terminology_repository import TerminologyRepository

        term_repo = TerminologyRepository()
        sql_repo = SqlExampleRepository()

        if self.term_vector_store is not None:
            await self.term_vector_store.initialize_collection()
            all_term_entries = []
            for host, port in host_ports:
                terms = await term_repo.get_by_host_port(host=host, port=port)
                parents = {}
                children_map = {}
                for t in terms:
                    if t.pid is None:
                        parents[t.id] = t
                    else:
                        children_map.setdefault(t.pid, []).append(t)
                for pid, parent in parents.items():
                    children = children_map.get(pid, [])
                    all_term_entries.append(
                        {
                            "id": parent.id,
                            "word": parent.word,
                            "description": parent.description or "",
                            "other_words": [c.word for c in children],
                            "specific_ds": parent.specific_ds,
                            "datasource_host": parent.datasource_host,
                            "datasource_port": parent.datasource_port,
                            "enabled": parent.enabled,
                        }
                    )
            if all_term_entries:
                await self.term_vector_store.batch_index(all_term_entries)
                logger.info(f"_sync_terms_and_sqls: indexed {len(all_term_entries)} terms")

        if self.sql_example_vector_store is not None:
            await self.sql_example_vector_store.initialize_collection()
            all_sql_entries = []
            for host, port in host_ports:
                sqls = await sql_repo.get_by_host_port(host=host, port=port)
                for s in sqls:
                    all_sql_entries.append(
                        {
                            "id": s.id,
                            "sql": s.sql or "",
                            "description": s.description or "",
                            "datasource_host": s.datasource_host,
                            "datasource_port": s.datasource_port,
                            "enabled": s.enabled,
                        }
                    )
            if all_sql_entries:
                await self.sql_example_vector_store.batch_index(all_sql_entries)
                logger.info(f"_sync_terms_and_sqls: indexed {len(all_sql_entries)} SQL examples")

    def get_cursors(self) -> dict[str, dict]:
        """获取所有检索器"""
        all_cursors = {}

        # 收集所有知识库的检索器
        for db_instance in self.db_instances.values():
            cursors = db_instance.get_cursors()
            all_cursors.update(cursors)

        return all_cursors
