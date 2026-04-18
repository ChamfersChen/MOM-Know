"""Java 系统 Token 管理服务"""

import httpx
from dataclasses import dataclass
from datetime import datetime

from yuxi.config import java_config
from yuxi.storage.redis.client import redis_client
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger


@dataclass
class JavaTokenData:
    """Java Token 数据结构"""

    access_token: str
    refresh_token: str | None
    tenant_id: str
    tenant_name: str | None
    created_at: str
    expires_in: int | None = None


class JavaTokenService:
    """Java Token 管理服务"""

    KEY_PREFIX = "java_token"

    def _get_key(self, user_id: int, tenant_id: str) -> str:
        """生成 Redis key"""
        return f"{self.KEY_PREFIX}:{user_id}:{tenant_id}"

    async def save_token(self, user_id: int, token_data: JavaTokenData, ttl: int | None = None) -> bool:
        """保存 Java Token 到 Redis"""
        if not java_config.enabled:
            logger.debug("Java 集成未启用，跳过保存 token")
            return True

        key = self._get_key(user_id, token_data.tenant_id)
        ttl = ttl or java_config.token_ttl

        data = {
            "access_token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "tenant_id": token_data.tenant_id,
            "tenant_name": token_data.tenant_name,
            "created_at": token_data.created_at,
            "expires_in": token_data.expires_in,
        }

        success = await redis_client.set_json_async(key, data, ex=ttl)
        if success:
            logger.info(f"Java token 已保存: user_id={user_id}, tenant_id={token_data.tenant_id}")
        else:
            logger.error(f"Java token 保存失败: user_id={user_id}")
        return success

    async def get_token(self, user_id: int, tenant_id: str) -> JavaTokenData | None:
        """获取 Java Token"""
        if not java_config.enabled:
            return None

        key = self._get_key(user_id, tenant_id)
        data = await redis_client.get_json_async(key)

        if not data:
            return None

        return JavaTokenData(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            tenant_id=data.get("tenant_id", tenant_id),
            tenant_name=data.get("tenant_name"),
            created_at=data.get("created_at", ""),
            expires_in=data.get("expires_in"),
        )

    async def get_token_by_user(self, user_id: int) -> JavaTokenData | None:
        """根据 user_id 获取 Token（假设只有一个租户）"""
        if not java_config.enabled:
            return None

        pattern = f"{self.KEY_PREFIX}:{user_id}:*"
        keys = redis_client.raw.keys(pattern)

        if not keys:
            return None

        key = keys[0]
        data = await redis_client.get_json_async(key)

        if not data:
            return None

        return JavaTokenData(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            tenant_id=data.get("tenant_id", ""),
            tenant_name=data.get("tenant_name"),
            created_at=data.get("created_at", ""),
            expires_in=data.get("expires_in"),
        )

    async def delete_token(self, user_id: int, tenant_id: str) -> bool:
        """删除 Java Token"""
        key = self._get_key(user_id, tenant_id)
        result = await redis_client.delete_async(key)
        logger.info(f"Java token 已删除: user_id={user_id}, tenant_id={tenant_id}")
        return result > 0

    async def get_remaining_ttl(self, user_id: int, tenant_id: str) -> int:
        """获取 token 剩余有效期（秒）"""
        key = self._get_key(user_id, tenant_id)
        return await redis_client.ttl_async(key)

    async def validate_token(self, user_id: int, tenant_id: str) -> bool:
        """验证 token 有效性（通过调用 Java API）"""
        token_data = await self.get_token(user_id, tenant_id)
        if not token_data:
            return False

        try:
            url = f"{java_config.api_base_url}/admin/user/info_out"
            headers = {
                "Tenant-Id": token_data.tenant_id,
                "Authorization": f"Bearer {token_data.access_token}",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30.0)

            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                await self.delete_token(user_id, tenant_id)
                return False
            else:
                logger.warning(f"Java API 验证失败: status={response.status_code}")
                return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await self.delete_token(user_id, tenant_id)
            logger.error(f"Java API HTTP 错误: {e.response.status_code}")
            return False
        except Exception as e:
            logger.error(f"Java API 请求错误: {e}")
            return False

    async def get_status(self, user_id: int, tenant_id: str) -> dict:
        """获取 token 状态"""
        token_data = await self.get_token(user_id, tenant_id)

        if not token_data:
            return {
                "bound": False,
                "tenant_id": None,
                "tenant_name": None,
                "expires_in": None,
            }

        remaining_ttl = await self.get_remaining_ttl(user_id, tenant_id)

        return {
            "bound": True,
            "tenant_id": token_data.tenant_id,
            "tenant_name": token_data.tenant_name,
            "expires_in": max(0, remaining_ttl) if remaining_ttl > 0 else 0,
        }


java_token_service = JavaTokenService()
