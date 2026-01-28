"""PostgreSQL 知识库模型 - KnowledgeBase、KnowledgeFile、评估相关表"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.storage.postgres.models_business import Base
from src.utils.datetime_utils import utc_now_naive

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class SqlDatabase(Base):
    """SQL数据库模型"""

    __tablename__ = "sql_database"
    __table_args__ = (UniqueConstraint("db_id", name="uq_sql_database_db_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    db_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    connect_info = Column(JSON_VALUE)
    db_type = Column(String(32), nullable=False, index=True)
    share_config = Column(JSON_VALUE)
    related_db_ids = Column(String(512), nullable=True, index=False)
    created_at = Column(DateTime(timezone=True), default=utc_now_naive)
    updated_at = Column(DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive)


class SqlDatabaseTable(Base):
    """知识文件模型"""

    __tablename__ = "sql_database_table"
    __table_args__ = (UniqueConstraint("table_id", name="uq_sql_database_table_table_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(String(64), unique=True, nullable=False, index=True)
    database_id = Column(String(64), ForeignKey("sql_database.db_id", ondelete="CASCADE"), nullable=False, index=True)
    # database_name = Column(String(512), nullable=False)
    tablename = Column(String(512), nullable=False)
    description = Column(String(512), nullable=False)
    is_choose = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now_naive)
    updated_at = Column(DateTime(timezone=True), default=utc_now_naive, onupdate=utc_now_naive)

