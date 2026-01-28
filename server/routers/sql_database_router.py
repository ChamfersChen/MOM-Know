# =================================
# 数据库连接和表选择接口
# =================================

import traceback

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.responses import FileResponse as StarletteFileResponse

from server.utils.auth_middleware import get_admin_user
from src.storage.db.models import User
# from src.sql_database import sql_database
from src import sql_database
from src.utils import logger

sql_db = APIRouter(prefix="/sql_database", tags=["sql database"])


@sql_db.get("/databases")
async def get_databases(
    current_user: User = Depends(get_admin_user)
    ):
    """获取所有数据库"""
    try:
        user_info = {"role": current_user.role, "department_id": current_user.department_id}
        return await sql_database.get_databases_by_user(user_info)
        # database = sql_database.get_databases()
        # return database
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}


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
        if await sql_database.database_name_exists(database_name):
            # return {"message": f"创建数据库失败 {e}", "status": "failed"}
            raise HTTPException(
                status_code=409,
                detail=f"知识库名称 '{database_name}' 已存在，请使用其他名称",
            )

        connect_info_dict = connect_info.model_dump() if hasattr(connect_info, "model_dump") else connect_info

        # sql_database.test_connection(connection_info)
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
    # current_user: User = Depends(get_admin_user)
    ):
    """获取数据库详细信息"""
    database = await sql_database.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@sql_db.delete("/database/{db_id}")
async def delete_database(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
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

@sql_db.get("/database/{db_id}/tables/selected")
async def get_tables(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
    ):
    logger.debug(f"GET tables info in {db_id}")

    try:
        info = await sql_database.get_selected_tables(db_id)
        return info
    except Exception as e:
        logger.error(f"Failed to get selected table info, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to get selected table info", "status": "failed"}

@sql_db.post("/database/{db_id}/tables/choose")
async def choose_tables(
    db_id: str, 
    table_ids: list[str] = Body(...), 
    current_user: User = Depends(get_admin_user)
):
    try:
        if not table_ids:
            raise Exception("Table IDs cannot be empty")
        # 选择需要使用的表
        table_info = await sql_database.select_tables(db_id, table_ids)
        from src.agents import agent_manager
        await agent_manager.reload_all()
        return table_info
    except Exception as e:
        logger.error(f"Failed to choose tables, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to choose tables", "status": "failed"}

@sql_db.delete("/database/{db_id}/tables/{table_id}")
async def unchoose_tables(
    db_id: str, 
    table_id: str, 
    # current_user: User = Depends(get_admin_user)
):
    """取消选择数据库表"""
    logger.debug(f"Unchoose tables for db_id {db_id}: {table_id}")
    try:
        if not table_id:
            raise Exception("Table IDs cannot be empty")

        table_info = await sql_database.unselect_table(db_id, table_id)
        from src.agents import agent_manager
        await agent_manager.reload_all()
        return table_info
    except Exception as e:
        logger.error(f"Failed to unchoose tables, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to unchoose tables", "status": "failed"}

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