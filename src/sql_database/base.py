import os
import time
from abc import ABC, abstractmethod
from typing import Any
from src.utils import logger, hashstr
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat

class DnowledgeBaseException(Exception):
    """数据库库统一异常基类"""

    pass


class DBNotFoundError(DnowledgeBaseException):
    """数据库库不存在错误"""

    pass


class DBOperationError(DnowledgeBaseException):
    """数据库库操作错误"""

    pass


class ConnectorBase(ABC):
    """知识库抽象基类，定义统一接口"""

    # 类级别的处理队列，跟踪所有正在处理的文件
    _processing_files = set()
    _processing_lock = None

    def __init__(self, work_dir: str):
        """
        初始化知识库

        Args:
            work_dir: 工作目录
        """
        import threading

        self.work_dir = work_dir
        self.databases_meta: dict[str, dict] = {}
        self.tables_meta: dict[str, dict] = {}
        self.selected_tables_meta: dict[str, dict] = {}
        # self.topk: int = 5
        # self.similarity_threshold: float = 0.2

        # 初始化类级别的锁
        if ConnectorBase._processing_lock is None:
            ConnectorBase._processing_lock = threading.Lock()

        os.makedirs(work_dir, exist_ok=True)

        # 自动加载元数据
        # self._load_metadata()
        # self._normalize_metadata_state()

    async def _load_metadata(self):
        from src.repositories.sql_database_repository import SqlDatabaseRepository
        from src.repositories.sql_database_tables_repository import SqlDatabaseTableRepository

        db_repo = SqlDatabaseRepository()
        table_repo = SqlDatabaseTableRepository()

        databases = [db for db in await db_repo.get_all() if db.db_type == self.db_type]
        self.databases_meta = {
            db.db_id: {
                "name": db.name,
                "description": db.description,
                "db_type": db.db_type,
                "connect_info": db.connect_info,
                "share_config": db.share_config,
                "related_db_ids": db.related_db_ids.split(";") if db.related_db_ids else [],
                "created_at": utc_isoformat(db.created_at) if db.created_at else utc_isoformat(),
            }
            for db in databases
        }
        logger.debug(f"databases meta: {self.databases_meta}")
        self.tables_meta = {}
        for db in databases:
            for record in await table_repo.list_by_db_id(db.db_id):
                self.tables_meta[record.table_id] = {
                    "table_id": record.table_id,
                    "database_id": record.database_id,
                    "tablename": record.tablename,
                    "description": record.description,
                    "is_choose": record.is_choose,
                    "total_description": record.total_description,
                    "created_at": utc_isoformat(record.created_at) if record.created_at else None,
                    "updated_at": utc_isoformat(record.updated_at) if record.updated_at else None,
                }

        logger.info(f"Loaded {self.db_type} metadata from database for {len(self.databases_meta)} databases")

    @staticmethod
    def _normalize_timestamp(value: Any) -> str | None:
        """Convert persisted timestamps to a normalized UTC ISO string."""
        try:
            dt_value = coerce_any_to_utc_datetime(value)
        except (TypeError, ValueError) as exc:  # noqa: BLE001
            logger.warning(f"Invalid timestamp encountered: {value!r} ({exc})")
            return None

        if not dt_value:
            return None
        return utc_isoformat(dt_value)

    def _normalize_metadata_state(self) -> None:
        """Ensure in-memory metadata uses normalized timestamp formats."""
        for meta in self.databases_meta.values():
            if "created_at" in meta:
                normalized = self._normalize_timestamp(meta.get("created_at"))
                if normalized:
                    meta["created_at"] = normalized

        for table_info in self.tables_meta.values():
            if "created_at" in table_info:
                normalized = self._normalize_timestamp(table_info.get("created_at"))
                if normalized:
                    table_info["created_at"] = normalized

        for table_info in self.selected_tables_meta.values():
            if "created_at" in table_info:
                normalized = self._normalize_timestamp(table_info.get("created_at"))
                if normalized:
                    table_info["created_at"] = normalized

    @property
    @abstractmethod
    def db_type(self) -> str:
        """知识库类型标识"""
        pass


    @abstractmethod
    async def _create_connection(self) -> Any:
        """
        初始化底层知识库实例

        Args:
            instance: 底层知识库实例
        """
        pass

    @abstractmethod
    def get_cursor(self):
        pass


    async def move_table(self, db_id: str, table_id: str, new_parent_id: str | None) -> dict:
        """
        Move a file or folder to a new parent folder.

        Args:
            db_id: Database ID
            file_id: File/Folder ID to move
            new_parent_id: New parent folder ID (None for root)

        Returns:
            dict: Updated metadata
        """
        if table_id not in self.tables_meta:
            raise ValueError(f"Tables {table_id} not found")

        meta = self.tables_meta[table_id]
        if meta.get("database_id") != db_id:
            raise ValueError(f"File {table_id} does not belong to database {db_id}")

        # Basic cycle detection for folders
        if meta.get("is_folder") and new_parent_id:
            # Check if new_parent_id is a child of file_id (or is file_id itself)
            if new_parent_id == table_id:
                raise ValueError("Cannot move a folder into itself")

            # Walk up the tree from new_parent_id
            current = new_parent_id
            while current:
                parent_meta = self.files_meta.get(current)
                if not parent_meta:
                    break  # Should not happen if integrity is maintained
                if current == table_id:
                    raise ValueError("Cannot move a folder into its own subfolder")
                current = parent_meta.get("parent_id")

        meta["parent_id"] = new_parent_id
        await self._save_metadata()
        return meta


    async def create_database(
        self,
        database_name: str,
        description: str,
        connect_info: dict | None = None,
        share_config: dict | None = None,
        related_db_ids: str | None = None,
        **kwargs,
    ) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数

        Returns:
            数据库信息字典
        """

        # 从 kwargs 中获取 is_private 配置
        is_private = kwargs.get("is_private", False)
        prefix = "db_private_" if is_private else "db_"
        db_id = f"{prefix}{hashstr(database_name, with_salt=True, length=32)}"

        # 创建数据库记录
        # 确保 Pydantic 模型被转换为字典，以便 JSON 序列化
        connect_info['port'] = int(connect_info['port'])
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "db_type": self.db_type,
            "connect_info": connect_info.model_dump() if hasattr(connect_info, "model_dump") else connect_info,
            "share_config": share_config,
            "related_db_ids": related_db_ids if related_db_ids else [],
            "created_at": utc_isoformat(),
        }
        await self._save_metadata()

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 返回数据库信息
        db_dict = self.databases_meta[db_id].copy()
        db_dict["db_id"] = db_id
        db_dict["tables"] = {}

        return db_dict

    def delete_database(self, db_id: str) -> dict:
        """
        删除数据库

        Args:
            db_id: 数据库ID

        Returns:
            操作结果
        """
        if db_id in self.databases_meta:
            # 删除相关文件记录
            tables_to_delete = [fid for fid, finfo in self.tables_meta.items() if finfo.get("database_id") == db_id]
            for table_id in tables_to_delete:
                del self.tables_meta[table_id]
            tables_to_delete = [
                fid for fid, finfo in self.selected_tables_meta.items()
                if finfo.get("database_id") == db_id
            ]
            for table_id in tables_to_delete:
                del self.selected_tables_meta[table_id]

            # 删除数据库记录
            del self.databases_meta[db_id]
            self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            import shutil

            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    def get_database_info(self, db_id: str) -> dict | None:
        """
        获取数据库详细信息

        Args:
            db_id: 数据库ID

        Returns:
            数据库信息或None
        """
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

        # 获取文件信息
        db_tables = {}
        for table_id, table_info in self.tables_meta.items():
            if table_info.get("database_id") == db_id:
                created_at = self._normalize_timestamp(table_info.get("created_at"))
                db_tables[table_id] = {
                    "database_id": db_id,
                    "table_id": table_info.get("table_id", ""),
                    "tablename": table_info.get("tablename", ""),
                    "description": table_info.get("description", ""),
                    "is_choose": table_info.get("is_choose", False),
                    "total_description": table_info.get("total_description", ""),
                    "created_at": created_at,
                }

        # 按创建时间倒序排序文件列表
        sorted_tables = dict(
            sorted(
                db_tables.items(),
                key=lambda item: item[1].get("created_at") or "",
                reverse=True,
            )
        )

        meta["tables"] = sorted_tables
        meta["row_count"] = len(sorted_tables)
        meta["status"] = "已连接"
        return meta

    def _serialize_metadata(self, obj):
        """递归序列化元数据中的 Pydantic 模型"""
        if hasattr(obj, "dict"):
            return obj.dict()
        elif isinstance(obj, dict):
            return {k: self._serialize_metadata(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_metadata(item) for item in obj]
        else:
            return obj

    async def _save_metadata(self):
        """保存元数据"""
        from src.repositories.sql_database_repository import SqlDatabaseRepository
        from src.repositories.sql_database_tables_repository import SqlDatabaseTableRepository

        db_repo = SqlDatabaseRepository()
        table_repo = SqlDatabaseTableRepository()

        self._normalize_metadata_state()

        for db_id, meta in self.databases_meta.items():
            existing = await db_repo.get_by_id(db_id)
            payload = {
                "db_id": db_id,
                "name": meta.get("name") or db_id,
                "description": meta.get("description"),
                "db_type": meta.get("db_type") or self.db_type,
                "connect_info": meta.get("connect_info"),
                "share_config": meta.get("share_config"),
                "related_db_ids": ";".join(meta.get("related_db_ids",[])),
            }
            if existing is None:
                await db_repo.create(payload)
            else:
                await db_repo.update(
                    db_id,
                    {
                        "name": payload["name"],
                        "description": payload["description"],
                        "db_type": payload["db_type"],
                        "connect_info": payload["connect_info"],
                        "share_config": payload["share_config"],
                        "related_db_ids": payload["related_db_ids"]
                    },
                )

        for table_id, table_info in self.tables_meta.items():
            existing_table = await table_repo.get_by_table_id(table_id)
            database_id = table_info["database_id"]
            # existing_table = await table_repo.get_by_table_name(table_name)
            payload = {
                "table_id": table_id,
                "database_id": database_id,
                "tablename": table_info.get("tablename", ""),
                "description": table_info.get("description", ""),
                "is_choose": table_info.get("is_choose", False),
                "total_description": table_info.get("total_description", ""),
            }
            if existing_table is None:
                await table_repo.create(payload)
            else:
                await table_repo.update(
                    table_id,
                    {
                        "tablename": payload["tablename"],
                        "description": payload["description"],
                        "is_choose": payload["is_choose"],
                        "total_description": payload["total_description"],
                    },
                )


    def prepare_table_metadata(self, db_id: str) -> dict:
        """
        准备文件或URL的元数据
        """
        db_name = self.databases_meta[db_id]['name']
        table_id = f"table_{hashstr(str(db_name) + str(time.time()), 6)}"

        return {
            "database_id": db_id,
            "created_at": utc_isoformat(),
            "table_id": table_id,
        }

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
