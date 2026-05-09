"""MOM 系统 API 工具模块

提供 call_mom_api 和 list_mom_endpoints 工具，让 Agent 能够调用 MOM 系统的 API 接口。
认证信息（tenant_id 和 token）自动从 Redis 中获取，无需 Agent 感知。
"""

import json
import os

import httpx
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field
from typing import Annotated, Any
from fuzzywuzzy import fuzz
from typing import List

from yuxi.agents.toolkits.registry import tool
from yuxi.config import java_config
from yuxi.services.java_token_service import java_token_service
from yuxi.utils.logging_config import logger

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]

# 端点注册表文件路径
_ENDPOINT_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "endpoint_registry.json")


def fuzzy_match_keywords(keywords: List[str], content: List[str], top_k: int = 5) -> List[str]:
    """
    将 keywords 中每个关键词与 content 进行模糊匹配，取 top_k 并去重后返回。
    
    Args:
        keywords: 关键词列表
        content: 待匹配的内容列表
        top_k: 每个关键词取前 k 个匹配结果
    
    Returns:
        去重后的匹配结果列表
    """
    seen = set()
    results = []

    for keyword in keywords:
        # 计算每个 content 与当前 keyword 的相似度
        scores = [
            (item, fuzz.partial_ratio(keyword, item))
            for item in content
        ]
        # 按相似度降序排列，取 top_k
        top_matches = sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]

        for item, score in top_matches:
            if item not in seen:
                seen.add(item)
                results.append(item)

    return results


def _load_endpoint_registry() -> list[dict]:
    """从 JSON 文件加载端点注册表"""
    if not os.path.exists(_ENDPOINT_REGISTRY_PATH):
        logger.warning(f"端点注册表文件不存在: {_ENDPOINT_REGISTRY_PATH}")
        return []
    try:
        with open(_ENDPOINT_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载端点注册表失败: {e}")
        return []


class MomApiInput(BaseModel):
    """MOM 系统 API 调用参数"""

    endpoint: str = Field(
        description=(
            "API 端点路径，不要包含前导斜杠。\n"
            "如果不确定端点或参数格式，请先调用 list_mom_endpoints 工具查询。"
        ),
    )
    method: str = Field(
        default="GET",
        description="HTTP 方法，支持 GET（查询数据）、POST（创建数据）、PUT（更新数据）、DELETE（删除数据）。",
    )
    body: dict | None = Field(
        default=None,
        description=(
            "请求体（JSON 格式），仅 POST 和 PUT 时使用。"
            "创建公告: {title, content, startTime, endTime, organizationId}；"
            "创建日程: {title, description, startTime, endTime}。"
            "GET 请求时为 null。"
        ),
    )
    query_params: dict | None = Field(
        default=None,
        description="URL 查询参数，如分页参数 {current: 1, size: 10}、筛选条件等。GET 请求时常用。",
    )


@tool(
    category="mom_api",
    tags=["MOM系统", "API"],
    display_name="调用MOM系统API",
    args_schema=MomApiInput,
)
async def call_mom_api(
    endpoint: str,
    method: str = "GET",
    body: dict | None = None,
    query_params: dict | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """调用 MOM 系统 API 接口。

    通过此工具可以与 MOM 主系统进行交互，包括查询用户信息、管理系统公告、
    管理日程、查询订单统计等操作。

    认证信息（tenant_id 和 token）自动从当前用户的会话中获取，无需手动传入。

    注意事项：
    - 如果先前对话中没有调用 list_mom_endpoints 工具，请先调用 list_mom_endpoints 工具查看完整端点列表。
    - GET 请求用于查询数据，不需要 body 参数，可使用 query_params 分页或筛选
    - POST/PUT 请求用于创建/更新数据，需要传入 body 参数
    - DELETE 请求用于删除数据
    - 如果提示认证过期，需要通知用户从 MOM 系统重新跳转登录

    """
    if not java_config.enabled:
        return json.dumps(
            {"success": False, "error": "MOM API 访问未启用，请联系管理员配置 MOM_ACCESS"},
            ensure_ascii=False,
        )

    method = method.upper()
    if method not in HTTP_METHODS:
        return json.dumps(
            {"success": False, "error": f"不支持的 HTTP 方法: {method}，支持的方法: {HTTP_METHODS}"},
            ensure_ascii=False,
        )

    runtime_context = runtime.context
    user_id = getattr(runtime_context, "user_id", None)
    if not user_id:
        return json.dumps({"success": False, "error": "无法获取当前用户信息"}, ensure_ascii=False)

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return json.dumps({"success": False, "error": f"用户 ID 格式错误: {user_id}"}, ensure_ascii=False)

    # 从 Redis 获取 MOM Token
    token_data = await java_token_service.get_token_by_user(user_id)
    if not token_data:
        return json.dumps(
            {
                "success": False,
                "error": "MOM 系统认证未同步，请从 MOM 系统跳转登录后重试。",
                "hint": "用户尚未绑定 MOM 系统账号，或认证已过期。请在页面上方点击'前往同步'按钮。",
            },
            ensure_ascii=False,
        )

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
                json=body,
                params=query_params,
            )

        if response.status_code == 401:
            await java_token_service.delete_token(user_id, token_data.tenant_id)
            return json.dumps(
                {
                    "success": False,
                    "error": "MOM 系统认证已过期，请从 MOM 系统重新跳转登录。",
                    "hint": "Token 已失效，需用户重新从 MOM 系统跳转。",
                },
                ensure_ascii=False,
            )
        error_message = "请求失败，请仔细查看 list_mom_endpoints 工具返回的端点信息，确认路径、方法和参数格式是否正确。\n"
        if response.status_code >= 400:
            error_detail = error_message
            try:
                error_data = response.json()
                error_detail += error_data.get("msg", error_data.get("message", str(error_data)))
            except Exception:
                error_detail += response.text[:500]

            logger.warning(f"MOM API 错误: {method} {url}, status={response.status_code}, detail={error_detail}")
            return json.dumps(
                {
                    "success": False,
                    "error": f"MOM API 请求失败 (HTTP {response.status_code})",
                    "detail": error_detail,
                },
                ensure_ascii=False,
            )

        try:
            result = response.json()
        except Exception:
            result = response.text

        logger.info(f"MOM API 成功: {method} {url}, status={response.status_code}")

        result_str = json.dumps({"success": True, "data": result}, ensure_ascii=False, default=str)
        max_length = 10000
        if len(result_str) > max_length:
            result_str = result_str[:max_length] + "\n...(结果已截断)"

        return result_str

    except httpx.TimeoutException:
        return json.dumps(
            {"success": False, "error": "MOM API 请求超时，请稍后重试"},
            ensure_ascii=False,
        )
    except httpx.ConnectError:
        return json.dumps(
            {"success": False, "error": f"无法连接 MOM 系统 ({java_config.api_base_url})，请检查网络或联系管理员"},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"MOM API 调用异常: {e}", exc_info=True)
        return json.dumps(
            {"success": False, "error": f"MOM API 调用异常: {str(e)}\n\n{error_message}"},
            ensure_ascii=False,
        )


class ListMomEndpointsInput(BaseModel):
    """查询 MOM 系统端点列表的参数"""

    keywords: list | None = Field(
        default=None,
        description="可选的关键词，用于模糊搜索端点路径或描述，帮助快速定位相关端点。例如输入 '公告' 可以筛选出与系统公告相关的端点。",
    )


@tool(
    category="mom_api",
    tags=["MOM系统", "API"],
    display_name="查询MOM系统端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_mom_endpoints( keywords: Annotated[list, "搜索关键词"],) -> str:
    """查询 MOM 系统 API 的可用端点列表及参数格式。
    可以按分类筛选，也可以获取全部端点。

    注意：如果先前对话中没有调用 list_mom_endpoints 工具，请先调用 list_mom_endpoints 工具查看完整端点列表。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    registry = _load_endpoint_registry()
    if not registry:
        return json.dumps(
            {"success": False, "error": "端点注册表为空或未配置"},
            ensure_ascii=False,
        )

    if keywords:
        # 使用fuzzywuzzy算法进行模糊匹配，提升搜索体验
        content = [f"{item.get('category', '')} {item.get('endpoint', '')} {item.get('description', '')}" for item in registry]
        filtered = fuzzy_match_keywords(keywords, content, top_k=5)
    else:
        filtered = registry

    if not filtered:
        return json.dumps(
            {
                "success": False,
                "error": f"未找到包含关键词 '{keywords}' 的端点",
            },
            ensure_ascii=False,
            )

    return json.dumps(
        {"success": True, "endpoints": registry, "count": len(registry)},
        ensure_ascii=False,
        default=str,
    )
