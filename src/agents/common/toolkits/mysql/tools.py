from copy import deepcopy
from typing import Annotated, Any

from pydantic import BaseModel, Field

from src.agents.common.toolkits.registry import tool
from src.utils import logger
from src.knowledge import graph_base

from .connection import (
    MySQLConnectionManager,
    QueryTimeoutError,
    execute_query_with_timeout,
    limit_result_size,
)
from .exceptions import MySQLConnectionError
from .security import MySQLSecurityChecker
from src.sql_database import sql_database, term_service

# 全局连接管理器实例
_connection_manager: MySQLConnectionManager | None = None
host_set = set()
port_set = set()

def get_connection_manager() -> MySQLConnectionManager:
    """获取全局连接管理器"""
    global _connection_manager
    if _connection_manager is None:
        import os

        # 从环境变量中读取 MySQL 配置
        mysql_config = {
            "host": os.getenv("MYSQL_HOST"),
            "user": os.getenv("MYSQL_USER"),
            "password": os.getenv("MYSQL_PASSWORD"),
            "database": os.getenv("MYSQL_DATABASE"),
            "port": int(os.getenv("MYSQL_PORT") or "3306"),
            "charset": "utf8mb4",
            "description": os.getenv("MYSQL_DATABASE_DESCRIPTION") or "默认 MySQL 数据库",
        }
        # 验证配置完整性
        required_keys = ["host", "user", "password", "database"]
        for key in required_keys:
            if not mysql_config[key]:
                raise MySQLConnectionError(
                    f"MySQL configuration missing required key: {key}, please check your environment variables."
                )

        _connection_manager = MySQLConnectionManager(mysql_config)
    return _connection_manager


class QueryModel(BaseModel):

    query: str = Field(description="改写后的用户问题", example="")


# @tool(name_or_callable="mysql_list_tables_with_query", description="根据用户问题查询表名及说明", args_schema=QueryModel)
@tool(
    category="mysql",
    tags=["数据库", "查询"],
    display_name="根据用户问题查询表名及说明",
    name_or_callable="mysql_list_tables_with_query",
    args_schema=QueryModel,
)
async def mysql_list_tables_with_query(
    query: Annotated[str, "改写后的用户问题"],
) -> str:
    """通过用户问题获取数据库中的所有表名

    这个工具通过实体列表来列出当前数据库中所有的表名，帮助你了解数据库的结构。
    """
    global host_set, port_set
    host_set.clear()
    port_set.clear()
    result = []
    logger.info(f">> 查询表名及说明 {query}")
    extras = mysql_list_tables_with_query.extras
    user_department = extras.get('user_department')
    try:
        query_results = graph_base.query_node(query, threshold=0.5, hops=4, max_entities=25)

        # 处理节点
        # tb_names = [n['name'] for n in query_results['nodes']]
        tb_names = []
        map_id_name = {}
        map_id_port_ip = {}
        for n in query_results['nodes']:
            tb_names.append(n['name'])
            map_id_name[n['id']] = n['name']
            map_id_port_ip[n['id']] = f"{n['host']}:{n['port']}"
            host_set.add(n['host'])
            port_set.add(n['port'])

        assert len(host_set) == 1 and len(port_set) == 1, "查询结果中包含多个数据库连接信息，无法确定使用哪个连接查询表名"
        # loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(loop)
        # databases = loop.run_until_complete(sql_database.get_databases())
        databases = await sql_database.get_databases()
        unaccessible_databases = []
        for db_infos in databases.values():
            for db_info in db_infos:
                table_names = []
                db_desc = db_info['description']
                db_name = db_info['name']
                tables_info = db_info['tables']
                db_host = db_info['connect_info']['host']
                db_port = db_info['connect_info']['port']
                if not db_host in host_set or not db_port in port_set: # noqa E501
                    unaccessible_databases.append(f"{db_host}:{db_port}")
                    continue

                if not db_info['share_config']['is_shared'] and user_department not in db_info['share_config']['accessible_departments']: # noqa E501
                    unaccessible_databases.append(f"{db_host}:{db_port}")
                    continue

                if not tables_info.values():
                    continue

                for table_info in tables_info.values():
                    if f"{table_info['tablename']}" not in tb_names:
                        continue

                    table_name = f"`{table_info['tablename'].replace(".", "`.`")}`: {table_info['description']}"
                    table_names.append(table_name)
                if table_names:
                    result.append(f"数据库说明\n`{db_name}`: {db_desc}\n数据库中的表:\n{'\n'.join(table_names)}")

        db_entity_info = "\n---\n".join(result)

        # 处理关系
        database_edge_info = []
        t2t_edges = [e for e in query_results['edges'] if e['type'] == 'Table2Table']
        for edge in t2t_edges:
            source_name = map_id_name[edge['source_id']]
            target_name = map_id_name[edge['target_id']]

            if source_name == target_name:
                continue

            database_edge_info.append(f"`{source_name}` <--> `{target_name}`")
        db_relation_info = ""
        if database_edge_info:
            db_relation_info = f"数据库之间存在以下关系: \n{'\n'.join(database_edge_info)}"


        return f"{db_entity_info}\n===\n{db_relation_info}" if len(result) else "您所在的部门没有可以访问的数据库，请联系管理员，添加数据库。" # noqa E501
    except Exception as e:
        error_msg = f"获取表名失败: {str(e)}"
        return error_msg

class TableListModel(BaseModel):
    """获取表名列表的参数模型"""

    pass


@tool(
    category="mysql",
    tags=["数据库", "查询"],
    display_name="列出MySQL表",
    name_or_callable="mysql_list_tables",
    args_schema=TableListModel,
)
def mysql_list_tables() -> str:
    """【查询表名及说明】获取数据库中的所有表名

    这个工具用来列出当前数据库中所有的表名，帮助你了解数据库的结构。
    """
    global host_set, port_set
    result = []
    try:
        databases = sql_database.get_databases()
        for db_infos in databases.values():
            for db_info in db_infos:
                table_names = []
                db_desc = db_info['description']
                db_name = db_info['connection_info']['database']
                tables_info = db_info['selected_tables']
                db_host = db_info['connect_info']['host']
                db_port = db_info['connect_info']['port']
                if not db_host in host_set or not db_port in port_set: # noqa E501
                    continue
                if not tables_info.values():
                    continue
                for table_info in tables_info.values():
                    table_name = f"{db_name}.{table_info['table_name']}: {table_info['table_comment']}"
                    table_names.append(table_name)
                result.append(f"数据库说明\n{db_name}: {db_desc}\n数据库中的表:\n{'\n'.join(table_names)}")

        return "\n---\n".join(result)
    except Exception as e:
        error_msg = f"获取表名失败: {str(e)}"
        return error_msg


class TableDescribeModel(BaseModel):
    """获取表结构的参数模型"""

    database_name: str = Field(description="要查询的数据库名", example="users")
    table_name: str = Field(description="要查询的表名", example="users")


@tool(
    category="mysql",
    tags=["数据库", "结构"],
    display_name="描述MySQL表结构",
    name_or_callable="mysql_describe_table", description="获得描述表",
    args_schema=TableDescribeModel,
)
async def mysql_describe_table(
        database_name: Annotated[str, "要查询的数据库名"],
        table_name: Annotated[str, "要查询结构的表名"]
    ) -> str:
    """获取指定表的详细结构信息

    这个工具用来查看表的字段信息、数据类型、是否允许NULL、默认值、键类型等。
    帮助你了解表的结构，以便编写正确的SQL查询。
    """
    global host_set, port_set
    host = deepcopy(host_set).pop() if len(host_set) == 1 else None
    port = deepcopy(port_set).pop() if len(port_set) == 1 else None
    assert host and port, "数据库连接信息为空."
    try:
        # 验证表名安全性
        if not MySQLSecurityChecker.validate_table_name(table_name):
            return "表名包含非法字符，请检查表名"

        # conn_manager = get_connection_manager()
        db_id = sql_database.db_name_to_id[database_name]
        host_port_name = f"{host}:{port}/{database_name}"
        db_id = sql_database.db_host_port_name_to_id[host_port_name]
        db_instance = await sql_database._get_db_for_database(db_id)
        with db_instance.get_cursor(db_id) as cursor:
            # 获取表结构
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()

            if not columns:
                return f"表 {table_name} 不存在或没有字段"

            # 获取字段备注信息
            column_comments: dict[str, str] = {}
            try:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_COMMENT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                    """,
                    (table_name, database_name),
                )
                comment_rows = cursor.fetchall()
                for row in comment_rows:
                    column_name = row.get("COLUMN_NAME")
                    if column_name:
                        column_comments[column_name] = row.get("COLUMN_COMMENT") or ""
            except Exception as e:
                logger.warning(f"Failed to fetch column comments for table {table_name}: {e}")

            # 格式化输出
            result = f"表 `{table_name}` 的结构:\n\n"
            result += "字段名\t\t类型\t\tNULL\t键\t默认值\t\t额外\t备注\n"
            result += "-" * 80 + "\n"

            for col in columns:
                field = col["Field"] or ""
                type_str = col["Type"] or ""
                null_str = col["Null"] or ""
                key_str = col["Key"] or ""
                default_str = col.get("Default") or ""
                extra_str = col.get("Extra") or ""
                comment_str = column_comments.get(field, "")

                # 格式化输出
                result += (
                    f"{field:<16}\t{type_str:<16}\t{null_str:<8}\t{key_str:<4}\t"
                    f"{default_str:<16}\t{extra_str:<16}\t{comment_str}\n"
                )

            # 获取索引信息
            try:
                cursor.execute(f"SHOW INDEX FROM `{table_name}`")
                indexes = cursor.fetchall()

                if indexes:
                    result += "\n索引信息:\n"
                    index_dict = {}
                    for idx in indexes:
                        key_name = idx["Key_name"]
                        if key_name not in index_dict:
                            index_dict[key_name] = []
                        index_dict[key_name].append(idx["Column_name"])

                    for key_name, columns in index_dict.items():
                        result += f"- {key_name}: {', '.join(columns)}\n"
            except Exception as e:
                logger.warning(f"Failed to get index info for table {table_name}: {e}")

            logger.info(f"Retrieved structure for table {table_name}")
            return result

    except Exception as e:
        error_msg = f"获取表 {table_name} 结构失败: {str(e)}"
        logger.error(error_msg)
        return error_msg


class QueryModel(BaseModel):
    """执行SQL查询的参数模型"""

    database_names: list[str] = Field(description="要查询的数据库名称列表", example='["system", "users"]')
    sql: str = Field(description="要执行的SQL查询语句（只能是SELECT语句）", example="SELECT * FROM users WHERE id = 1")
    timeout: int | None = Field(default=60, description="查询超时时间（秒），默认60秒，最大600秒", ge=1, le=600)


@tool(
    category="mysql",
    tags=["数据库", "SQL"],
    display_name="执行MySQL查询",
    name_or_callable="mysql_query", description="执行 SQL 查询",
    args_schema=QueryModel,
)
async def mysql_query(
    database_names: Annotated[list[str], "要查询的数据库名称列表"], # noqa E501 TODO 可能存在同一个连接跨数据库表查询的问题，需要判断是否为一个连接
    sql: Annotated[str, "要执行的SQL查询语句（只能是SELECT语句, 且需要带上数据库名, 如：SELECT * FROM db1.table1）"],
    timeout: Annotated[int | None, "查询超时时间（秒），默认60秒，最大600秒"] = 60,
) -> str:
    """【执行 SQL 查询】执行只读的SQL查询语句

    这个工具用来执行SQL查询并返回结果。支持复杂的SELECT查询，包括JOIN、GROUP BY等。
    注意：只能执行查询操作，不能修改数据。

    参数:
    - sql: SQL查询语句
    - timeout: 查询超时时间（防止长时间运行的查询）
    """
    global host_set, port_set
    host = deepcopy(host_set).pop() if len(host_set) == 1 else None
    port = deepcopy(port_set).pop() if len(port_set) == 1 else None
    assert host and port, "数据库连接信息为空."
    try:
        # 验证SQL安全性
        if not MySQLSecurityChecker.validate_sql(sql):
            return "SQL语句包含不安全的操作或可能的注入攻击，请检查SQL语句"

        if not MySQLSecurityChecker.validate_timeout(timeout):
            return "timeout参数必须在1-600之间"

        # conn_manager = get_connection_manager()
        # connection = conn_manager.get_connection()

        database_name = database_names[0] # 获得同一个连接下的其中一个数据库名
        # db_id = sql_database.db_name_to_id[database_name]
        host_port_name = f"{host}:{port}/{database_name}"
        db_id = sql_database.db_host_port_name_to_id[host_port_name]
        connection = await sql_database.get_connection(db_id)

        effective_timeout = timeout or 60
        try:
            result = execute_query_with_timeout(connection, sql, timeout=effective_timeout)
        except QueryTimeoutError as timeout_error:
            logger.error(f"MySQL query timed out after {effective_timeout} seconds: {timeout_error}")
            raise
        except Exception:
            sql_database.invalidate_connection(db_id)
            raise

        if not result:
            return "查询执行成功，但没有返回任何结果"

        # 限制结果大小
        limited_result = limit_result_size(result, max_chars=10000)

        # 检查结果是否被截断
        if len(limited_result) < len(result):
            warning = f"\n\n⚠️ 警告: 查询结果过大，只显示了前 {len(limited_result)} 行（共 {len(result)} 行）。\n"
            warning += "建议使用更精确的查询条件或使用LIMIT子句来减少返回的数据量。"
        else:
            warning = ""

        # 格式化输出
        if limited_result:
            # 获取列名
            columns = list(limited_result[0].keys())

            # 计算每列的最大宽度
            col_widths = {}
            for col in columns:
                col_widths[col] = max(len(str(col)), max(len(str(row.get(col, ""))) for row in limited_result))
                col_widths[col] = min(col_widths[col], 50)  # 限制最大宽度

            # 构建表头
            header = "| " + " | ".join(f"{col:<{col_widths[col]}}" for col in columns) + " |"
            separator = "|" + "|".join("-" * (col_widths[col] + 2) for col in columns) + "|"

            # 构建数据行
            rows = []
            for row in limited_result:
                row_str = "| " + " | ".join(f"{str(row.get(col, '')):<{col_widths[col]}}" for col in columns) + " |"
                rows.append(row_str)

            result_str = f"查询结果（共 {len(limited_result)} 行）:\n\n"
            result_str += header + "\n" + separator + "\n"
            result_str += "\n".join(rows[:50])  # 最多显示50行

            if len(rows) > 50:
                result_str += f"\n\n... 还有 {len(rows) - 50} 行未显示 ..."

            result_str += warning

            logger.info(f"Query executed successfully, returned {len(limited_result)} rows")
            return result_str

        return "查询执行成功，但返回数据为空"

    except Exception as e:
        error_msg = f"SQL查询执行失败: {str(e)}\n\n{sql}"

        # 提供更有用的错误信息
        if "timeout" in str(e).lower():
            error_msg += "\n\n💡 建议：查询超时了，请尝试以下方法：\n"
            error_msg += "1. 减少查询的数据量（使用WHERE条件过滤）\n"
            error_msg += "2. 使用LIMIT子句限制返回行数\n"
            error_msg += "3. 增加timeout参数值（最大600秒）"
        elif "table" in str(e).lower() and "doesn't exist" in str(e).lower():
            error_msg += "\n\n💡 建议：表不存在，请使用 mysql_list_tables 查看可用的表名"
        elif "column" in str(e).lower() and "doesn't exist" in str(e).lower():
            error_msg += "\n\n💡 建议：列不存在，请使用 mysql_describe_table 查看表结构"
        elif "not enough arguments for format string" in str(e).lower():
            error_msg += (
                "\n\n💡 建议：SQL 中的百分号 (%) 被当作参数占位符使用。"
                " 如需匹配包含百分号的文本，请将百分号写成双百分号 (%%) 或使用参数化查询。"
            )

        logger.error(error_msg)
        return error_msg


def _get_db_description() -> str:
    """获取数据库描述"""
    import os

    return os.getenv("MYSQL_DATABASE_DESCRIPTION") or ""


# 用于跟踪是否已注入描述，避免重复
_db_description_injected: bool = False


def _inject_db_description(tools: list[Any]) -> None:
    """将数据库描述注入到工具描述中"""
    global _db_description_injected
    if _db_description_injected:
        return

    db_desc = _get_db_description()
    if not db_desc:
        return

    for _tool in tools:
        if hasattr(_tool, "description"):
            # 在描述末尾添加数据库说明
            _tool.description = f"{_tool.description}\n\n当前数据库说明: {db_desc}"

    _db_description_injected = True


def get_mysql_tools() -> list[Any]:
    """获取MySQL工具列表"""
    tools = [mysql_list_tables_with_query, mysql_describe_table, mysql_query]
    # tools = [mysql_list_tables, mysql_describe_table, mysql_query]
    _inject_db_description(tools)
    return tools
