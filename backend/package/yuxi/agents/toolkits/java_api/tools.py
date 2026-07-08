"""MOM 系统 API 工具模块

提供 call_mom_api 和 list_mom_endpoints 工具，让 Agent 能够调用 MOM 系统的 API 接口。
认证信息（tenant_id 和 token）自动从 Redis 中获取，无需 Agent 感知。
"""

import json
import os

import httpx
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field
from fuzzywuzzy import fuzz
from typing import List

from yuxi.agents.toolkits.registry import tool
from yuxi.config import java_config
from yuxi.services.java_token_service import java_token_service
from yuxi.utils.logging_config import logger

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
REMOVE_KEYS = [
    "files",
    "updateTime",
    "createTime",
    "updateBy",
    "createBy",
    "remark",
    "tenantId",
    "organizationId",
    "parentId",
    "weight",
]  # 需要从结果中移除的字段，避免返回过多无用信息


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
        (
            item,
            fuzz.partial_ratio(
                rewritten_query, f"{item.get('category', '')} {item.get('endpoint', '')} {item.get('description', '')}"
            ),
        )
        for item in content
    ]
    top_matches = sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]

    for item, score in top_matches:
        results.append(item)

    return results


def _load_endpoint_registry(endpoint_path: str) -> list[dict]:
    """从 JSON 文件加载端点注册表"""
    if not os.path.exists(endpoint_path):
        logger.warning(f"端点注册表文件不存在: {endpoint_path}")
        return []
    try:
        with open(endpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载端点注册表失败: {e}")
        return []


async def list_endpoints(rewritten_query: str, endpoint_json_filepath: str) -> str:
    registry = _load_endpoint_registry(endpoint_json_filepath)
    if not registry:
        return json.dumps(
            {"success": False, "error": "端点注册表为空或未配置"},
            ensure_ascii=False,
        )

    if rewritten_query:
        # 使用fuzzywuzzy算法进行模糊匹配，提升搜索体验
        filtered = fuzzy_match_keywords(rewritten_query, registry, top_k=10)
    else:
        filtered = registry

    if not filtered:
        return json.dumps(
            {
                "success": False,
                "error": f"未找到与 {rewritten_query} 相关的端点",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"success": True, "endpoints": filtered, "count": len(registry)},
        ensure_ascii=False,
        default=str,
    )


class MomApiInput(BaseModel):
    """MOM 系统 API 调用参数"""

    endpoint: str = Field(
        description=(
            "API 端点路径，不要包含前导斜杠。\n如果不确定端点或参数格式，请先调用 list_mom_endpoints 工具查询。"
        ),
    )
    method: str = Field(
        default="GET",
        description="HTTP 方法，支持 GET（查询数据）、POST（创建数据）、PUT（更新数据）、DELETE（删除数据）。",
    )
    body: dict | str | None = Field(
        default=None,
        description=(
            "请求体（JSON 格式），仅 POST 和 PUT 时使用。"
            "创建公告: {title, content, startTime, endTime, organizationId}；"
            "创建日程: {title, description, startTime, endTime}。"
            "GET 请求时为 null。"
        ),
    )
    query_params: dict | str | None = Field(
        default=None,
        description="URL 查询参数，如分页参数 {current: 1, size: 10}、筛选条件等。GET 请求时常用。",
    )


@tool(
    category="buildin",
    tags=["MOM系统", "API"],
    display_name="调用系统API",
    args_schema=MomApiInput,
)
async def call_api(
    endpoint: str,
    method: str = "GET",
    body: dict | str | None = None,
    query_params: dict | str | None = None,
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

    def remove_none_fields(obj, remove_keys=None):
        """
        递归删除:
        1. value 为 None 的字段
        2. key 在 remove_keys 中的字段
        """

        remove_keys = set(remove_keys or [])

        if isinstance(obj, dict):
            return {
                k: remove_none_fields(v, remove_keys) for k, v in obj.items() if v is not None and k not in remove_keys
            }

        elif isinstance(obj, list):
            return [remove_none_fields(i, remove_keys) for i in obj]

        return obj

    error_message = "请求失败，请仔细查看工具返回的端点信息，确认路径、方法和参数格式是否正确。\n"
    extra_message = ""
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
    user_id = getattr(runtime_context, "uid", None)
    if not user_id:
        return json.dumps({"success": False, "error": "无法获取当前用户信息"}, ensure_ascii=False)

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
    # url = f"{java_config.api_base_url}/api/{endpoint.lstrip('/')}"
    url = f"{java_config.api_base_url}/{endpoint.lstrip('/')}"
    headers = {
        "Tenant-Id": token_data.tenant_id,
        "Authorization": f"Bearer {token_data.access_token}",
        "Accept": "application/json, text/plain, */*",
    }

    logger.info(f"MOM API 调用: {method} {url}, user_id={user_id}")

    try:
        if isinstance(body, str):
            body = json.loads(body)
        if isinstance(query_params, str):
            query_params = json.loads(query_params)

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
            logger.debug(f"MOM API 返回值: {method} {url}, result={result}")

            # 移除结果中的权限信息
            if data := result.get("data", {}):
                if isinstance(data, dict):
                    if "permissions" in data:
                        del result["data"]["permissions"]
                    if "sysUser" in data and isinstance(data["sysUser"], dict):
                        # 对 dsScope 字段进行解释
                        ds_scope = data.get("sysUser", {}).get("dsScope")
                        if ds_scope is not None:
                            extra_message = f"\n\n注意：返回结果中的 dsScope 字段值({ds_scope})为“当前用户能够访问的组织ID列表”, 可请求"

            # 清理结果中的 None 值，避免返回过多无用信息

            result = remove_none_fields(result, remove_keys=REMOVE_KEYS)
            if method not in ["GET"]:
                result_str = json.dumps(
                    {"success": True, "data": result, "refresh": True}, ensure_ascii=False, default=str
                )
            else:
                result_str = json.dumps({"success": True, "data": result}, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"MOM API 返回值处理错误: {method} {url}, error={e}")
            result = response.text
            result_str = json.dumps({"success": True, "data": result}, ensure_ascii=False, default=str)

        logger.info(f"MOM API 成功: {method} {url}, status={response.status_code}")

        # 对结果进行长度限制，避免返回过长内容导致模型处理困难
        # max_length = 10000
        # if len(result_str) > max_length:
        #     result_str = result_str[:max_length] + "\n...(结果已截断)"

        return result_str + extra_message

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


async def list_endpoints(rewritten_query: str, endpoint_json_filepath: str) -> str:
    registry = _load_endpoint_registry(endpoint_json_filepath)
    if not registry:
        return json.dumps(
            {"success": False, "error": "端点注册表为空或未配置"},
            ensure_ascii=False,
        )

    if rewritten_query:
        # 使用fuzzywuzzy算法进行模糊匹配，提升搜索体验
        filtered = fuzzy_match_keywords(rewritten_query, registry, top_k=10)
    else:
        filtered = registry

    if not filtered:
        return json.dumps(
            {
                "success": False,
                "error": f"未找到与 {rewritten_query} 相关的端点",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"success": True, "endpoints": filtered, "count": len(registry)},
        ensure_ascii=False,
        default=str,
    )
