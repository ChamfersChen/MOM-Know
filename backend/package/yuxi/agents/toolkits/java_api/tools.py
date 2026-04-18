"""MOM 系统 API 工具模块

提供 call_mom_api 和 list_mom_endpoints 工具，让 Agent 能够调用 MOM 系统的 API 接口。
认证信息（tenant_id 和 token）自动从 Redis 中获取，无需 Agent 感知。
"""

import json
import os

import httpx
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field

from yuxi.agents.toolkits.registry import tool
from yuxi.config import java_config
from yuxi.services.java_token_service import java_token_service
from yuxi.utils.logging_config import logger

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]

# 端点注册表文件路径
_ENDPOINT_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "endpoint_registry.json")


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
            "API 端点路径，不要包含前导斜杠。"
            "常用端点如下：\n"
            "【用户管理】\n"
            "- admin/user/info_out (GET): 获取当前用户信息，无需参数\n"
            "- admin/user/page (GET): 获取用户列表\n"
            "  query_params: {current: 页码, size: 每页数量, keyword?: 关键词}\n"
            "\n"
            "【系统公告】\n"
            "- admin/sysNews (POST): 创建系统公告\n"
            "  body: {title: 公告标题, content: 公告内容, startTime: 开始时间, endTime: 结束时间, organizationId: 工厂ID}\n"
            "- admin/sysNews/page (GET): 分页查询公告\n"
            "  query_params: {current: 页码, size: 每页数量}\n"
            "\n"
            "【日程管理】\n"
            "- admin/schedule (POST): 创建日程\n"
            "  body: {title: 日程标题, description: 日程描述, startTime: 开始时间, endTime: 结束时间}\n"
            "- admin/schedule/page (GET): 分页查询日程\n"
            "  query_params: {current: 页码, size: 每页数量}\n"
            "\n"
            "【订单统计】\n"
            "- admin/order/statistics (GET): 获取订单统计信息\n"
            "  query_params: {factoryId: 工厂ID}\n"
            "\n"
            "【角色管理】\n"
            "- admin/role/page (GET): 分页查询角色\n"
            "  query_params: {current: 页码, size: 每页数量}\n"
            "\n"
            "【菜单管理】\n"
            "- admin/menu (GET): 获取菜单列表\n"
            "\n"
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
    - GET 请求用于查询数据，不需要 body 参数，可使用 query_params 分页或筛选
    - POST/PUT 请求用于创建/更新数据，需要传入 body 参数
    - DELETE 请求用于删除数据
    - 如果提示认证过期，需要通知用户从 MOM 系统重新跳转登录

    常用端点及参数格式：

    【用户管理】
    - admin/user/info_out (GET): 获取当前用户信息，无需参数
    - admin/user/page (GET): 获取用户列表
      query_params: {current: 页码, size: 每页数量, keyword?: 关键词}

    【系统公告】
    - admin/sysNews (POST): 创建系统公告
      body: {title: 标题, content: 内容, startTime: 开始时间(YYYY-MM-DD), endTime: 结束时间(YYYY-MM-DD), organizationId: 工厂ID}
    - admin/sysNews/page (GET): 分页查询公告
      query_params: {current: 页码, size: 每页数量}

    【日程管理】
    - admin/schedule (POST): 创建日程
      body: {title: 标题, description: 描述, startTime: 开始时间(YYYY-MM-DD HH:mm:ss), endTime: 结束时间}
    - admin/schedule/page (GET): 分页查询日程
      query_params: {current: 页码, size: 每页数量}

    【订单统计】
    - admin/order/statistics (GET): 获取订单统计信息
      query_params: {factoryId: 工厂ID}

    【角色管理】
    - admin/role/page (GET): 分页查询角色
      query_params: {current: 页码, size: 每页数量}

    如果不确定端点或参数格式，请先调用 list_mom_endpoints 工具查看完整端点列表。
    """
    if not java_config.enabled:
        return json.dumps(
            {"success": False, "error": "MOM API 访问未启用，请联系管理员配置 JAVA_ACCESS"},
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

        if response.status_code >= 400:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = error_data.get("msg", error_data.get("message", str(error_data)))
            except Exception:
                error_detail = response.text[:500]

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
            {"success": False, "error": f"MOM API 调用异常: {str(e)}"},
            ensure_ascii=False,
        )


class ListMomEndpointsInput(BaseModel):
    """查询 MOM 系统端点列表的参数"""

    category: str | None = Field(
        default=None,
        description="按分类筛选端点，如 '用户管理'、'系统公告'、'日程管理'、'订单统计' 等。不传则返回全部。",
    )


@tool(
    category="mom_api",
    tags=["MOM系统", "API"],
    display_name="查询MOM系统端点列表",
    args_schema=ListMomEndpointsInput,
)
async def list_mom_endpoints(category: str | None = None) -> str:
    """查询 MOM 系统 API 的可用端点列表及参数格式。

    当你不确定某个功能对应的端点路径或请求参数格式时，调用此工具获取完整的端点信息。
    可以按分类筛选，也可以获取全部端点。

    返回内容包括：端点路径、HTTP 方法、参数格式说明、简要描述。
    """
    registry = _load_endpoint_registry()
    if not registry:
        return json.dumps(
            {"success": False, "error": "端点注册表为空或未配置"},
            ensure_ascii=False,
        )

    if category:
        filtered = [ep for ep in registry if ep.get("category") == category]
        if not filtered:
            available_categories = list({ep.get("category", "未分类") for ep in registry})
            return json.dumps(
                {
                    "success": False,
                    "error": f"未找到分类 '{category}' 的端点",
                    "available_categories": available_categories,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {"success": True, "endpoints": filtered, "count": len(filtered)},
            ensure_ascii=False,
            default=str,
        )

    return json.dumps(
        {"success": True, "endpoints": registry, "count": len(registry)},
        ensure_ascii=False,
        default=str,
    )
