import os

from yuxi.config import config
from yuxi.sql_database.factory import DBConnectorBaseFactory
from yuxi.sql_database.implementations.mysql import MySQLConnector
from yuxi.sql_database.manager import SqlDataBaseManager
from yuxi.services.term_service import TermService
from yuxi.services.sql_example_service import SqlExampleService

# 注册知识库类型
# KnowledgeBaseFactory.register(
#   "chroma", ChromaKB, {"description": "基于 ChromaDB 的轻量级向量知识库，适合开发和小规模"}
# )
DBConnectorBaseFactory.register("mysql", MySQLConnector, {"description": "MySQL 数据库连接器"})
# KnowledgeBaseFactory.register(
#   "lightrag", LightRagKB, {"description": "基于图检索的知识库，支持实体关系构建和复杂查询"}
#)

# 创建知识库管理器
work_dir = os.path.join(config.save_dir, "sql_database_data")
sql_database = SqlDataBaseManager(work_dir)
term_service = TermService()
sql_example_service = SqlExampleService()

__all__ = ["sql_database"]
