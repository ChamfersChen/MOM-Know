# =================================
# 数据库连接和表选择接口
# =================================

import traceback

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from server.utils.auth_middleware import get_admin_user

from yuxi.storage.postgres.models_business import User

# from yuxi.knowledge import graph_base
from yuxi.utils.logging_config import logger
from yuxi.storage.postgres.models_terminology import TerminologyInfo
from yuxi.storage.postgres.models_sql_examples import SqlExampleInfo
from yuxi.sql_database import sql_database, term_service, sql_example_service
from yuxi.utils.sql_password_crypto import sql_password_crypto

sql_database_router = APIRouter(prefix="/sql_database", tags=["sql database"])


def _mask_connect_info_for_log(connect_info: dict | None) -> dict:
    """脱敏连接信息，避免日志输出明文密码。"""
    if not isinstance(connect_info, dict):
        return {}

    safe_connect_info = dict(connect_info)
    if "password" in safe_connect_info:
        safe_connect_info["password"] = "***"
    if "password_encrypted" in safe_connect_info:
        safe_connect_info["password_encrypted"] = "***"
    return safe_connect_info


def _normalize_connect_info(connect_info: dict) -> dict:
    """标准化连接信息，兼容明文与密文密码输入。"""
    connect_info_dict = connect_info.model_dump() if hasattr(connect_info, "model_dump") else dict(connect_info or {})

    encrypted_password = connect_info_dict.pop("password_encrypted", None)
    if encrypted_password:
        connect_info_dict["password"] = sql_password_crypto.decrypt_password(encrypted_password)

    return connect_info_dict


class DatasourceConnectionInfo(BaseModel):
    host: str
    port: int


class TermQueryInfo(BaseModel):
    query: str
    ds_host: str
    ds_port: int


@sql_database_router.get("/password/public_key")
async def get_sql_password_public_key(
    current_user: User = Depends(get_admin_user),
):
    """获取 SQL 数据源密码加密公钥。"""
    return {
        "algorithm": "RSA-OAEP-256",
        "public_key": sql_password_crypto.get_public_key_pem(),
    }


@sql_database_router.get("/databases")
async def get_databases(current_user: User = Depends(get_admin_user)):
    """获取所有数据库"""
    try:
        user_info = {"role": current_user.role, "department_id": current_user.department_id}
        return await sql_database.get_databases_by_user(user_info)
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}


@sql_database_router.post("/databases/reupload")
async def reupload(datasource_group: list[str] = Body(None), current_user: User = Depends(get_admin_user)):
    """清空全部旧数据，根据选择的数据源组重新导入 Milvus + Neo4j 并激活。"""
    if not datasource_group:
        return {"message": "未选择数据源", "data": [], "code": 1}

    # 1. 清空 Milvus（表/术语/SQL 示例）和 Neo4j
    try:
        await sql_database.clear_all_sql_data()
    except Exception as e:
        logger.error(f"清空 SQL 数据失败: {e}, {traceback.format_exc()}")
        return {"message": f"清空 SQL 数据失败: {e}", "data": [], "code": 1}

    # 2. 更新激活状态
    from yuxi.repositories.sql_database_repository import SqlDatabaseRepository

    repo = SqlDatabaseRepository()
    await repo.deactivate_all_except(datasource_group)
    for db_id in datasource_group:
        await repo.update(db_id, {"is_activate": True})

    # 3. 批量重索引
    try:
        await sql_database.batch_reindex_all(datasource_group)
        results = [{"db_id": db_id, "status": "success", "message": "重索引完成"} for db_id in datasource_group]
    except Exception as e:
        logger.error(f"批量重索引失败: {e}, {traceback.format_exc()}")
        results = [{"db_id": db_id, "status": "failed", "message": str(e)} for db_id in datasource_group]

    sql_database.set_active_db_ids(datasource_group)

    failed = [r for r in results if r["status"] == "failed"]
    code = 1 if failed else 0
    return {"message": f"完成 {len(results)} 个数据源重索引，{len(failed)} 个失败", "data": results, "code": code}


@sql_database_router.post("/check_connection")
async def check_connection(
    database_name: str = Body(...),
    connect_info: dict = Body(None),
    db_type: str = Body("mysql"),
    current_user: User = Depends(get_admin_user),
):
    """创建数据库"""
    logger.debug(f"Check connection connect_info {_mask_connect_info_for_log(connect_info)}, datasource_type {db_type}")
    try:
        connect_info_dict = _normalize_connect_info(connect_info)

        # 先检查名称是否已存在
        if await sql_database.database_ip_port_name_exists(connect_info_dict):
            return {"message": f"数据库连接校验失败。'{database_name}' 已存在，请使用其他名称", "status": "failed"}

        # 验证数据库连接信息
        sql_database.test_connection(connect_info_dict)
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"数据库连接校验失败，请检查连接信息是否正确。", "status": "failed"}

    return {"message": "连接成功", "status": "success"}


@sql_database_router.post("/database")
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
        f"Create database {database_name} with kb_type {db_type}, connect_info {_mask_connect_info_for_log(connect_info)}"
    )
    try:
        connect_info_dict = _normalize_connect_info(connect_info)

        # 先检查名称是否已存在
        if await sql_database.database_ip_port_name_exists(connect_info_dict):
            return {"message": f"创建数据库失败", "status": "failed"}
            # raise HTTPException(
            #     status_code=409,
            #     detail=f"知识库名称 '{database_name}' 已存在，请使用其他名称",
            # )

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
        from yuxi.agents.buildin import agent_manager

        await agent_manager.reload_all()

        return database_info
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"创建数据库失败 {e}", "status": "failed"}


@sql_database_router.get("/database/{db_id}")
async def get_database_info(db_id: str, current_user: User = Depends(get_admin_user)):
    """获取数据库详细信息"""
    database = await sql_database.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database


@sql_database_router.delete("/database/{db_id}")
async def delete_database(db_id: str, current_user: User = Depends(get_admin_user)):
    """删除数据库"""
    logger.debug(f"Delete database {db_id}")
    try:
        await sql_database.delete_database(db_id)

        # 需要重新加载所有智能体，因为工具刷新了
        from yuxi.agents.buildin import agent_manager

        await agent_manager.reload_all()

        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除数据库失败: {e}")


@sql_database_router.put("/database/{db_id}/tables")
async def update_tables(db_id: str, table_info: dict = Body(...), current_user: User = Depends(get_admin_user)):
    """更新数据库表信息"""
    try:
        info = await sql_database.update_tables(db_id, table_info)
        return {"message": "更新成功", "data": info, "code": 0}
    except Exception as e:
        logger.error(f"更新数据库表失败 {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": f"更新失败: {e}", "code": 1}


@sql_database_router.post("/tables/search")
async def search_tables(
    query: str = Body(...),
    db_ids: list[str] | None = Body(None),
    top_k: int = Body(10),
    search_mode: str = Body("hybrid"),
    is_choose_only: bool = Body(False),
    similarity_threshold: float = Body(0.0),
    vector_weight: float = Body(0.7),
    bm25_weight: float = Body(0.3),
    reranker_model: str | None = Body(None),
    use_graph_retrieval: bool = Body(False),
    graph_weight: float = Body(0.5),
    search_terms: bool = Body(False),
    search_sqls: bool = Body(False),
    current_user: User = Depends(get_admin_user),
):
    """基于用户问题检索数据库表，并可同时检索相关术语和 SQL 示例。"""
    try:
        result = await sql_database.search_tables(
            query=query,
            db_ids=db_ids,
            top_k=top_k,
            search_mode=search_mode,
            is_choose_only=is_choose_only,
            similarity_threshold=similarity_threshold,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            reranker_model=reranker_model,
            use_graph_retrieval=use_graph_retrieval,
            graph_weight=graph_weight,
            search_terms=search_terms,
            search_sqls=search_sqls,
        )
        return {"message": "success", "data": result, "code": 0}
    except Exception as e:
        logger.error(f"搜索数据库表失败 {e}, {traceback.format_exc()}")
        return {"message": f"搜索失败: {e}", "data": {"tables": [], "terms": [], "sqls": []}, "code": 1}


@sql_database_router.put("/database/{db_id}")
async def update_database_info(
    db_id: str,
    name: str = Body(...),
    description: str = Body(...),
    share_config: dict = Body(None),
    related_db_ids: str | list[str] = Body(None),
    current_user: User = Depends(get_admin_user),
):
    """更新知识库信息"""
    logger.debug(
        f"[update_database_info] db_id={db_id}, name={name}, "
        f"description={description}, share_config={share_config}, "
        f"related_db_ids={related_db_ids}"
    )
    try:
        database = await sql_database.update_database(
            db_id,
            name,
            description,
            share_config=share_config,
            related_db_ids=related_db_ids,
        )
        return {"message": "更新成功", "data": database, "code": 0}
    except Exception as e:
        logger.error(f"更新数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"更新失败: {e}", "code": 1}


class HostPostInfo(BaseModel):
    host: str
    port: int


# 术语接口
@sql_database_router.post("/term")
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


@sql_database_router.put("/term")
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


@sql_database_router.delete("/term/{id}")
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


@sql_database_router.get("/term/query")
async def get_terms_info_with_query(
    term_query_info: TermQueryInfo = Body(...),
):
    """根据查询语句获取术语"""
    try:
        terms = await term_service.get_terms_with_query(
            term_query_info.query, term_query_info.ds_host, term_query_info.ds_port
        )
        return {"message": "success", "data": terms, "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")


@sql_database_router.get("/terms")
async def get_terms_info():
    """根据查询语句获取术语"""
    try:
        all_terms = await term_service.get_all_terminology()
        return {"message": "success", "data": list(all_terms.values()), "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")


@sql_database_router.get("/term/{host}/{port}")
async def get_terms_with_host_port_info(host: str, port: int):
    """根据查询语句获取术语"""
    try:
        all_terms = await term_service.get_terminologies_by_host_port(host=host, port=port)
        return {"message": "success", "data": list(all_terms.values()), "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")


@sql_database_router.put("/term/{term_id}/enable/{enable}")
async def enable_term(term_id: int, enable: bool):
    """根据查询语句获取术语"""
    try:
        term = await term_service.enable_terminology(term_id, enable)
        return {"message": "success", "data": term, "code": 0}
    except Exception as e:
        logger.error(f"启用术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"启用术语失败: {e}")


# sql示例接口
@sql_database_router.get("/sqls")
async def get_sqls():
    """根据查询语句获取术语"""
    try:
        all_sqls = await sql_example_service.get_all_sql_examples()
        return {"message": "success", "data": all_sqls, "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")


@sql_database_router.get("/sqls/{host}/{port}")
async def get_sqls_by_host_port(host: str, port: int):
    """根据查询语句获取术语"""
    try:
        all_sqls = await sql_example_service.get_sql_example_by_host_port(host=host, port=port)
        return {"message": "success", "data": all_sqls, "code": 0}
    except Exception as e:
        logger.error(f"获取术语失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"获取术语失败: {e}")


@sql_database_router.post("/sql")
async def create_sql(
    sql_model: SqlExampleInfo = Body(...),
):
    """添加SQL示例"""
    try:
        sqls = await sql_example_service.create_sql_example(sql_model)
        return {"message": "添加成功", "data": sqls, "code": 0}
    except Exception as e:
        logger.error(f"添加SQL示例失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"添加SQL示例失败: {e}")


@sql_database_router.put("/sql/{sql_id}/enable/{enable}")
async def enable_sql(sql_id: int, enable: bool):
    """根据查询语句获取术语"""
    try:
        sql = await sql_example_service.enable_sql_example(sql_id, enable)
        return {"message": "success", "data": sql, "code": 0}
    except Exception as e:
        logger.error(f"启用SQL示例失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"启用SQL示例失败: {e}")


@sql_database_router.put("/sql")
async def update_sql_info(
    sql_model: SqlExampleInfo = Body(...),
):
    """更新SQL示例"""
    try:
        sql = await sql_example_service.update_sql_example(sql_model)
        return {"message": "更新成功", "data": sql, "code": 0}
    except Exception as e:
        logger.error(f"更新SQL示例失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"更新SQL示例失败: {e}")


@sql_database_router.delete("/sql/{id}")
async def delete_sql_example(
    id: int,
):
    """删除SQL示例"""
    try:
        await sql_example_service.delete_by_id(int(id))
        return {"message": "删除成功", "code": 0}
    except Exception as e:
        logger.error(f"删除SQL示例失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除SQL示例失败: {e}")


@sql_database_router.post("/sql")
async def create_sql_example(
    sql_model: SqlExampleInfo = Body(...),
):
    """添加SQL示例"""
    print(sql_model)
    try:
        sqls = await sql_example_service.create_sql_example(sql_model)
        return {"message": "添加成功", "data": sqls, "code": 0}
    except Exception as e:
        logger.error(f"添加SQL示例失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"添加SQL示例失败: {e}")
