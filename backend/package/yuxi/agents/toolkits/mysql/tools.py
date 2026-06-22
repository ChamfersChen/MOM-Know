import json
import httpx
import traceback

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field
from .connection import (
    MySQLConnectionManager,
    QueryTimeoutError,
    execute_query_with_timeout,
    limit_result_size,
)
from .exceptions import MySQLConnectionError
from .security import MySQLSecurityChecker

from yuxi.config import java_config
from yuxi.services.java_token_service import java_token_service
from yuxi.services.java_token_service import java_token_service
from yuxi.agents.toolkits.registry import tool
from yuxi.utils import logger
from yuxi.sql_database import sql_database
from yuxi.storage.postgres.models_sql_examples import SqlExampleInfo

# 全局连接管理器实例
_connection_manager: MySQLConnectionManager | None = None
host_set = set()
port_set = set()

async def init_tenant_organization_info(
    runtime:ToolRuntime,
):
    runtime_context = runtime.context
    user_id = getattr(runtime_context, "uid", None)
    if not user_id:
        return False, "error: 无法获取当前用户信息", ""

    error_message = "请求失败，请仔细查看工具返回的端点信息，确认路径、方法和参数格式是否正确。\n"
    if not java_config.enabled:
        return False, "error: MOM API 访问未启用，请联系管理员配置 MOM_ACCESS", ""

    if not user_id:
        return False, "error: 无法获取当前用户信息", ""

    # 从 Redis 获取 MOM Token
    token_data = await java_token_service.get_token_by_user(user_id)
    if not token_data:
        return False, "error: MOM 系统认证未同步，请从 MOM 系统跳转登录后重试。用户尚未绑定 MOM 系统账号，或认证已过期。请在页面上方点击'前往同步'按钮。", ""

    endpoint = "admin/modelFactory/organization/list"
    method = "GET"
    # 构建请求
    url = f"{java_config.api_base_url}/{endpoint.lstrip('/')}"
    headers = {
        "Tenant-Id": token_data.tenant_id,
        "Authorization": f"Bearer {token_data.access_token}",
        "Accept": "application/json, text/plain, */*",
    }

    logger.info(f"MOM API 调用: {method} {url}, user_id={user_id}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
            )

        if response.status_code == 401:
            await java_token_service.delete_token(user_id, token_data.tenant_id)
            return False, "error: MOM 系统认证已过期，请从 MOM 系统重新跳转登录。Token 已失效，需用户重新从 MOM 系统跳转。", ""

        if response.status_code >= 400:
            error_detail = error_message
            try:
                error_data = response.json()
                error_detail += error_data.get("msg", error_data.get("message", str(error_data)))
            except Exception:
                error_detail += response.text[:500]

            logger.warning(f"MOM API 错误: {method} {url}, status={response.status_code}, detail={error_detail}")
            return False, f"error: MOM API 请求失败 (HTTP {response.status_code})" + error_detail, ""

        try:
            tenant_info = f"当前用户的 tenant_id={token_data.tenant_id} 注意在查询数据库表信息时，使用 tenant_id 来过滤查询结果。\n\n"

            result = response.json()

            # 对 dsScope 字段进行解释
            data = result.get('data', [])
            organization_info = []
            for d in data:
                org_id = d.get('value')
                org_name = d.get('label')
                if org_id and org_name:
                    organization_info.append(f"{org_name} (ID: {org_id})")
            result_str = f"当前用户所属的组织列表:\n{'\n'.join(organization_info)}" if organization_info else "未找到用户所属的组织信息，请确认 MOM 系统中该用户是否有组织信息。\n\n"
            result_str += "\n注意在查询数据库表信息时，使用组织ID来过滤查询结果。\n如果存在多个组织ID，需要询问用户查询哪个组织的表信息\n\n" if organization_info else ""
            return True, tenant_info, result_str

        except Exception as e:
            logger.error(f"MOM API 返回值处理错误: {method} {url}, error={e}")
            result = response.text
            return False, f"error: MOM API 返回值处理错误: {str(e)}\n\n返回内容: {result}", ""   

    except httpx.TimeoutException:
        return False, "error: MOM API 请求超时，请稍后重试", ""
    except httpx.ConnectError:
        return False, "error: 无法连接 MOM 系统 ({java_config.api_base_url})，请检查网络或联系管理员", ""
    except Exception as e:
        logger.error(f"MOM API 调用异常: {e}", exc_info=True)
        return False, f"error: MOM API 调用异常: {str(e)}\n\n{error_message}", ""


def convert_structure(data):
    result = []

    # 找父节点
    parents = [item for item in data if item["pid"] is None]

    for parent in parents:
        parent_id = parent["id"]

        # 找子节点
        children = [
            item["word"]
            for item in data
            if item["pid"] == parent_id
        ]

        result.append({
            "id": parent_id,
            "name": parent["word"],
            "description": parent["description"],
            "children": children
        })

    return result

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


class ListDbModel(BaseModel):
    query: str = Field(description="改写后的用户问题", example="")


@tool(
    category="buildin",
    tags=["数据库", "查询"],
    display_name="列出MySQL表",
    name_or_callable="mysql_list_tables_with_query",
    args_schema=ListDbModel,
)
async def mysql_list_tables_with_query(
    query: Annotated[str, "改写后的用户问题"],
    runtime: ToolRuntime = None,
) -> str:
    """通过用户问题获取数据库中的所有表名

    这个工具通过实体列表来列出当前数据库中所有的表名，帮助你了解数据库的结构。
    """
    global host_set, port_set
    host_set.clear()
    port_set.clear()
    logger.info(f">> 查询表名及说明 {query}")
    extras = mysql_list_tables_with_query.extras
    user_department = extras.get('user_department')
    success, tenant_info, organization_info = await init_tenant_organization_info(runtime)
    if not success:
        return tenant_info + organization_info
    try:
        await sql_database.initialize()
        query_results = await sql_database.search_tables(
            query=query, search_terms=True, search_sqls=True,
        )

        tables = query_results.get("tables", [])
        terms = query_results.get("terms", [])
        sqls = query_results.get("sqls", [])

        if not tables:
            return f"{tenant_info}{organization_info}未找到相关的数据库表信息。"

        # 按 db_id 分组，收集涉及的数据库
        grouped: dict[str, list[dict]] = {}
        db_ids_found: set[str] = set()
        for t in tables:
            db_id = t.get("db_id", "")
            db_ids_found.add(db_id)
            grouped.setdefault(db_id, []).append(t)

        # 获取数据库元信息并检查权限
        db_metas: dict[str, dict] = {}
        for db_id in db_ids_found:
            try:
                info = await sql_database.get_database_info(db_id)
                if info:
                    db_metas[db_id] = info
            except Exception:
                pass

        result_parts = []
        for db_id, db_tables in grouped.items():
            meta = db_metas.get(db_id)
            if not meta:
                continue

            share_config = meta.get("share_config") or {}
            if not share_config.get("is_shared", True):
                accessible = share_config.get("accessible_departments", [])
                if user_department not in accessible:
                    continue

            connect_info = meta.get("connect_info", {})
            host = connect_info.get("host")
            port = connect_info.get("port")
            if host and port is not None:
                host_set.add(host)
                port_set.add(int(port))

            db_name = meta.get("name", "")
            db_desc = meta.get("description", "")
            table_lines = []
            for t in db_tables:
                name = t.get("table_name", "")
                desc = t.get("content", "")
                if name:
                    table_lines.append(f"  - `{name}`: {desc}" if desc else f"  - `{name}`")
            if table_lines:
                part = f"数据库: {db_name}\n描述: {db_desc}\n表:\n" + "\n".join(table_lines)
                result_parts.append(part)

        if not result_parts:
            return f"{tenant_info}{organization_info}您所在的部门没有权限访问这些数据库，请联系管理员。"

        db_entity_info = "\n---\n".join(result_parts)

        # 格式化术语（去重）
        terms_text = ""
        if terms:
            seen_terms: dict[int, dict] = {}
            for t in terms:
                tid = t.get("id")
                if tid and int(tid) not in seen_terms:
                    seen_terms[int(tid)] = {
                        "name": t.get("word", ""),
                        "desc": t.get("description", ""),
                        "children": t.get("other_words", []),
                    }
            if seen_terms:
                lines = []
                for t in seen_terms.values():
                    if t["children"]:
                        lines.append(f"- `{t['name']}`: {t['desc']}, 同义词: {', '.join(t['children'])}")
                    else:
                        lines.append(f"- `{t['name']}`: {t['desc']}")
                terms_text = "\n===\n相关术语:\n" + "\n".join(lines)

        # 格式化 SQL 示例
        sqls_text = ""
        if sqls:
            lines = []
            for s in sqls:
                sql_str = s.get("sql", "")
                sql_desc = s.get("description", "")
                if sql_str:
                    lines.append(f"- `{sql_str}` — {sql_desc}" if sql_desc else f"- `{sql_str}`")
            if lines:
                sqls_text = "\n===\n相关 SQL 示例:\n" + "\n".join(lines)

        return f"{tenant_info}{organization_info}{db_entity_info}{terms_text}{sqls_text}"

    except Exception as e:
        error_msg = f"获取表名失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


class TableListModel(BaseModel):
    """获取表名列表的参数模型"""
    pass

class TableDescribeModel(BaseModel):
    """获取表结构的参数模型"""

    database_name: str = Field(description="要查询的数据库名", example="users")
    table_name: str = Field(description="要查询的表名", example="users")


@tool(
    category="buildin",
    tags=["数据库", "结构"],
    display_name="描述MySQL表结构",
    name_or_callable="mysql_describe_table", description="获得描述表",
    args_schema=TableDescribeModel,
)
async def mysql_describe_table(
        database_name: Annotated[str, "要查询的数据库名"],
        table_name: Annotated[str, "要查询结构的表名"],
        runtime: ToolRuntime = None,
    ) -> str:
    """获取指定表的详细结构信息

    这个工具用来查看表的字段信息、数据类型、是否允许NULL、默认值、键类型等。
    帮助你了解表的结构，以便编写正确的SQL查询。
    """
    global host_set, port_set
    host = deepcopy(host_set).pop() if len(host_set) == 1 else None
    port = deepcopy(port_set).pop() if len(port_set) == 1 else None
    if not (host and port):
        return "数据库连接信息为空. 请先使用'列出MySQL表'工具获取表名，确保连接信息正确."
    # 租户和组织信息提示
    success, tenant_info, organization_info = await init_tenant_organization_info(runtime)
    if not success:
        return tenant_info + organization_info
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
            return f"{tenant_info}{organization_info}{result}"

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
    category="buildin",
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
    if not (host and port):
        return "数据库连接信息为空. 请先使用'列出MySQL表'工具获取表名，确保连接信息正确."
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

class StoreSQLResult(BaseModel):
    query: str = Field(..., description="用户问题")
    sql: str = Field(..., description="最终能够回答用户问题的SQL语句")

# @tool(
#     category="mysql",
#     tags=["数据库", "SQL"],
#     display_name="自动存储Query与SQL结果",
#     name_or_callable="store_query_result", description="自动存储Query与SQL结果",
#     args_schema=StoreSQLResult,
# )
async def store_query_result(
    query: Annotated[str, "用户问题描述"], # noqa E501 TODO 可能存在同一个连接跨数据库表查询的问题，需要判断是否为一个连接
    sql: Annotated[str, "最终能够回答用户问题的SQL语句"],
) -> str:
    try:
        await sql_example_service.create_sql_example(
            SqlExampleInfo(
                sql=sql,
                description=query,
                create_time=datetime.now(), # .strftime("%Y-%m-%d %H:%M:%S"),
                datasource_host=deepcopy(host_set).pop() if len(host_set) == 1 else None,
                datasource_port=deepcopy(port_set).pop() if len(port_set) == 1 else None,
                enabled=True,
            )
        )
        return "SQL示例存储成功"
    except Exception as e:
        logger.error(f"存储SQL示例失败: {e}, {traceback.format_exc()}")
        return f"存储SQL示例失败: {str(e)}"



def get_mysql_tools() -> list[Any]:
    """获取MySQL工具列表"""
    tools = [mysql_list_tables_with_query, mysql_describe_table, mysql_query]
    # tools = [mysql_list_tables, mysql_describe_table, mysql_query]
    _inject_db_description(tools)
    return tools
