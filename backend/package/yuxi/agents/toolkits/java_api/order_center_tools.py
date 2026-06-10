"""MOM 系统 API 工具模块

提供 call_mom_api 和 list_mom_endpoints 工具，让 Agent 能够调用 MOM 系统的 API 接口。
认证信息（tenant_id 和 token）自动从 Redis 中获取，无需 Agent 感知。
"""

import os

from pydantic import BaseModel, Field
from fuzzywuzzy import fuzz
from typing import List

from yuxi.agents.toolkits.registry import tool

from .tools import list_endpoints

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
REMOVE_KEYS = ["files", "updateTime", "createTime", "updateBy", "createBy", "remark", "tenantId", 
               "organizationId", "parentId", "weight"]  # 需要从结果中移除的字段，避免返回过多无用信息

# 端点注册表文件路径
ORDER_CENTER_ORDER_ENDPOINTS_PATH = os.path.join(os.path.dirname(__file__), "endpoints/order_center/order_analyse.json")
ORDER_CENTER_SCHEDULE_ENDPOINTS_PATH = os.path.join(os.path.dirname(__file__), "endpoints/order_center/order_schedule.json")
ORDER_CENTER_SCHEDULE_UPDATE_ENDPOINTS_PATH = os.path.join(os.path.dirname(__file__), "endpoints/order_center/order_schedule_update.json")


def fuzzy_match_keywords(rewritten_query: str, content: List[dict], top_k: int = 5) -> List[dict]:
    """
    将 rewritten_query 中的查询与 content 中的value字段进行模糊匹配，取 top_k 并去重后返回。
    
    Args:
        rewritten_query: 改写后的查询字符串
        content: 待匹配的内容列表
        top_k: 每个关键词取前 k 个匹配结果
    
    Returns:
        去重后的匹配结果列表
    """
    results = []
    scores = [
        (item, fuzz.partial_ratio(rewritten_query, f"{item.get('category', '')} {item.get('endpoint', '')} {item.get('description', '')}"))
        for item in content
    ]
    top_matches = sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]

    for item, score in top_matches:
        results.append(item)

    return results

class ListMomEndpointsInput(BaseModel):
    """查询系统端点列表的参数"""

    rewritten_query: str = Field(
        default="",
        description="对原始用户问题进行的语义等价改写结果。用于提升模型对多样化表达的鲁棒性，或作为数据增强、问答一致性评估的输入。",
    )


@tool(
    category="mes_order_center",
    tags=["MOM系统", "API"],
    display_name="列出`订单分析功能`API端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_order_analyse_endpoints(rewritten_query: str = "") -> str:
    """查询`订单分析功能`相关的系统 API 列表及参数格式。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    return await list_endpoints(rewritten_query, ORDER_CENTER_ORDER_ENDPOINTS_PATH)


@tool(
    category="mes_order_center",
    tags=["MES系统", "API"],
    display_name="列出`创建排程工单功能`API端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_order_schedule_endpoints(rewritten_query: str = "") -> str:
    """查询`创建排程工单功能`相关的系统 API 列表及参数格式。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    return await list_endpoints(rewritten_query, ORDER_CENTER_SCHEDULE_ENDPOINTS_PATH)

@tool(
    category="mes_order_center",
    tags=["MES系统", "API"],
    display_name="列出`排程工单查询、修改和删除功能`API端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_order_schedule_update_endpoints(rewritten_query: str = "") -> str:
    """查询`排程工单查询、修改和删除功能`相关的系统 API 列表及参数格式。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    return await list_endpoints(rewritten_query, ORDER_CENTER_SCHEDULE_UPDATE_ENDPOINTS_PATH)