# =================================
# 数据库连接和表选择接口
# =================================

import traceback

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from server.utils.auth_middleware import get_admin_user

from src.storage.postgres.models_business import User
from src.knowledge import graph_base
from src import sql_database
from src.utils import logger
from src.storage.postgres.models_terminology import TerminologyInfo
from src.sql_database import term_service

sql_db = APIRouter(prefix="/sql_database", tags=["sql database"])

class DatasourceConnectionInfo(BaseModel):
    host: str
    port: int

class TermQueryInfo(BaseModel):
    query: str
    ds_host: str
    ds_port: int

@sql_db.get("/databases")
async def get_databases(
    current_user: User = Depends(get_admin_user)
    ):
    """获取所有数据库"""
    try:
        user_info = {"role": current_user.role, "department_id": current_user.department_id}
        return await sql_database.get_databases_by_user(user_info)
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}

# @sql_db.post("/databases/neo4j")
# async def create_graph(
#     current_user: User = Depends(get_admin_user)
#     ):
#     """获取所有数据库"""
#     try:
#         user_info = {"role": current_user.role, "department_id": current_user.department_id}
#         databases = await sql_database.get_databases_by_user(user_info)
#         databases_meta = databases['databases']
#         graph_base.delete_entity()
#         await graph_base.database_meta_add_entity(
#             databases_meta,
#             embed_model_name="siliconflow/BAAI/bge-m3",
#             batch_size=20
#         )
#         return {"message": "图谱创建成功", "code": 0}
#     except Exception as e:
#         logger.error(f"图谱创建失败 {e}, {traceback.format_exc()}")
#         graph_base.delete_entity()
#         return {"message": f"图谱创建失败 {e}", "code": 1}

@sql_db.post("/databases/neo4j")
async def create_graph(
    datasource_group: list = Body(None),
    current_user: User = Depends(get_admin_user)
    ):
    """根据选择的数据源组，创建图谱并使用该数据源进行问答"""
    try:
        graph_base.delete_entity()
        await graph_base.database_meta_add_entity(
            datasource_group,
            embed_model_name="siliconflow/BAAI/bge-m3",
            batch_size=20
        )
        return {"message": "图谱创建成功", "code": 0}
    except Exception as e:
        logger.error(f"图谱创建失败 {e}, {traceback.format_exc()}")
        graph_base.delete_entity()
        return {"message": f"图谱创建失败 {e}", "code": 1}


@sql_db.post("/check_connection")
async def check_connection(
    database_name: str = Body(...),
    connect_info: dict = Body(None),
    db_type: str = Body("mysql"),
    current_user: User = Depends(get_admin_user),
):
    """创建数据库"""
    logger.debug(
        f"Check connection connect_info {connect_info}, datasource_type {db_type}"
    )
    try:
        # 先检查名称是否已存在
        if await sql_database.database_ip_port_name_exists(connect_info):
            return {"message": f"数据库连接校验失败。'{database_name}' 已存在，请使用其他名称", "status": "failed"}

        connect_info_dict = connect_info.model_dump() if hasattr(connect_info, "model_dump") else connect_info

        # 验证数据库连接信息
        sql_database.test_connection(connect_info_dict)
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"数据库连接校验失败，请检查连接信息是否正确。", "status": "failed"}
    
    return {"message": "连接成功", "status": "success"}

@sql_db.post("/database")
async def create_database(
    database_name: str = Body(...),
    description: str = Body(...),
    connect_info: dict = Body(None),
    db_type: str = Body("mysql"),
    share_config: dict = Body(None),
    current_user: User = Depends(get_admin_user),
):
    """创建数据库"""
    logger.debug(
        f"Create database {database_name} with kb_type {db_type}, connect_info {connect_info}"
    )
    try:
        # 先检查名称是否已存在
        if await sql_database.database_ip_port_name_exists(connect_info):
            return {"message": f"创建数据库失败", "status": "failed"}
            # raise HTTPException(
            #     status_code=409,
            #     detail=f"知识库名称 '{database_name}' 已存在，请使用其他名称",
            # )

        connect_info_dict = connect_info.model_dump() if hasattr(connect_info, "model_dump") else connect_info

        # 验证数据库连接信息
        sql_database.test_connection(connect_info_dict)

        database_info = await sql_database.create_database(
            database_name,
            description,
            db_type,
            connect_info=connect_info_dict,
            share_config=share_config,
            )

        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager
        await agent_manager.reload_all()

        return database_info
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"创建数据库失败 {e}", "status": "failed"}


@sql_db.get("/database/{db_id}")
async def get_database_info(
    db_id: str,
    current_user: User = Depends(get_admin_user)
    ):
    """获取数据库详细信息"""
    database = await sql_database.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@sql_db.delete("/database/{db_id}")
async def delete_database(
    db_id: str,
    current_user: User = Depends(get_admin_user)
    ):
    """删除数据库"""
    logger.debug(f"Delete database {db_id}")
    try:
        await sql_database.delete_database(db_id)

        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager

        await agent_manager.reload_all()

        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除数据库失败: {e}")

@sql_db.put("/database/{db_id}/tables")
async def update_tables(
    db_id: str,
    table_info: dict = Body(...),
    current_user: User = Depends(get_admin_user)
    ):
    """更新数据库表信息"""

    try:
        info = await sql_database.update_tables(db_id, table_info)
        return info
    except Exception as e:
        logger.error(f"Failed to get table info, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to get table info", "status": "failed"}

@sql_db.put("/database/{db_id}")
async def update_database_info(
    db_id: str,
    name: str = Body(...),
    description: str = Body(...),
    share_config: dict = Body(None),
    related_db_ids: str = Body(None),
    current_user: User = Depends(get_admin_user),
):
    """更新知识库信息"""
    logger.debug(
        f"[update_database_info] 接收到的参数: name={name}"
    )
    try:
        database = await sql_database.update_database(
            db_id,
            name,
            description,
            share_config=share_config,
            related_db_ids=related_db_ids
        )
        return {"message": "更新成功", "database": database}
    except Exception as e:
        logger.error(f"更新数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"更新数据库失败: {e}")


# 术语接口
@sql_db.post("/term")
async def create_term_info(
    term_model: TerminologyInfo = Body(...),
):
    """添加术语"""
    try:
        terms = await term_service.create_terminology(term_model)
        return {"message": "添加成功", "data": terms, "code": 0}
    except Exception as e:
        logger.error(f"添加术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"添加术语失败: {e}")

@sql_db.put("/term")
async def update_term_info(
    term_model: TerminologyInfo = Body(...),
):
    """更新术语"""
    try:
        terms = await term_service.update_terminology(term_model)
        return {"message": "更新成功", "data": terms, "code": 0}
    except Exception as e:
        logger.error(f"更新术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"更新术语失败: {e}")

@sql_db.delete("/term/{id}")
async def delete_database_info(
    id: str,
):
    """添加术语"""
    try:
        await term_service.delete_by_id(int(id))
        return {"message": "删除成功", "code": 0}
    except Exception as e:
        logger.error(f"删除术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除术语失败: {e}")

@sql_db.get("/term/query")
async def get_terms_info_with_query(
    term_query_info: TermQueryInfo = Body(...),
):
    """根据查询语句获取术语"""
    try:
        terms = await term_service.get_terms_with_query(term_query_info.query, term_query_info.ds_host, term_query_info.ds_port)
        return {"message": "success", "data": terms, "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")

@sql_db.get("/term")
async def get_terms_info(
):
    """根据查询语句获取术语"""
    try:
        all_terms = await term_service.get_all_terminology()
        return {"message": "success", "data": list(all_terms.values()), "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")

@sql_db.put("/term/{term_id}/enable/{enable}")
async def enable_term(
    term_id: int,
    enable: bool
):
    """根据查询语句获取术语"""
    try:
        term = await term_service.enable_terminology(term_id, enable)
        return {"message": "success", "data": term, "code": 0}
    except Exception as e:
        logger.error(f"启用术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"启用术语失败: {e}")