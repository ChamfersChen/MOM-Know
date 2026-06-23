"""MOM 系统 API 工具模块

提供 call_mom_api 和 list_mom_endpoints 工具，让 Agent 能够调用 MOM 系统的 API 接口。
认证信息（tenant_id 和 token）自动从 Redis 中获取，无需 Agent 感知。
"""

import os

from pydantic import BaseModel, Field
from yuxi.agents.toolkits.registry import tool
from .tools import list_endpoints

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
REMOVE_KEYS = ["files", "updateTime", "createTime", "updateBy", "createBy", "remark", "tenantId", 
               "organizationId", "parentId", "weight"]  # 需要从结果中移除的字段，避免返回过多无用信息

# 端点注册表文件路径
HOME_ENDPOINTS_PATH = os.path.join(os.path.dirname(__file__), "endpoints/home/home_endpoints.json")


class ListMomEndpointsInput(BaseModel):
    """查询系统端点列表的参数"""

    rewritten_query: str = Field(
        default="",
        description="对原始用户问题进行的语义等价改写结果。用于提升模型对多样化表达的鲁棒性，或作为数据增强、问答一致性评估的输入。",
    )


@tool(
    category="buildin",
    tags=["MOM Home", "API"],
    display_name="列出`统一门户`API端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_home_endpoints(rewritten_query: str = "") -> str:
    """查询`订单分析功能`相关的系统 API 列表及参数格式。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    return await list_endpoints(rewritten_query, HOME_ENDPOINTS_PATH)
