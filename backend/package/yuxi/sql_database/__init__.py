import os

from yuxi.config import config
from yuxi.sql_database.factory import DBConnectorBaseFactory
from yuxi.sql_database.implementations.mysql import MySQLConnector
from yuxi.sql_database.manager import SqlDataBaseManager
from yuxi.sql_database.graphs import SqlDBGraphService
from yuxi.sql_database.vector_store import SqlTableVectorStore, TermVectorStore, SqlExampleVectorStore
from yuxi.services.term_service import TermService
from yuxi.services.sql_example_service import SqlExampleService

# 注册知识库类型
DBConnectorBaseFactory.register("mysql", MySQLConnector, {"description": "MySQL 数据库连接器"})

# 创建知识库管理器
work_dir = os.path.join(config.save_dir, "sql_database_data")
sql_database = SqlDataBaseManager(work_dir)

# 创建向量存储实例并绑定到管理器
sql_vector_store = SqlTableVectorStore()
sql_database.vector_store = sql_vector_store

# 创建图谱服务实例并绑定到管理器
sql_graph_service = SqlDBGraphService()
sql_database.graph_service = sql_graph_service

# 术语和 SQL 示例向量存储
term_vector_store = TermVectorStore()
term_service = TermService(vector_store=term_vector_store)
sql_database.term_vector_store = term_vector_store

sql_example_vector_store = SqlExampleVectorStore()
sql_example_service = SqlExampleService(vector_store=sql_example_vector_store)
sql_database.sql_example_vector_store = sql_example_vector_store

__all__ = ["sql_database"]
