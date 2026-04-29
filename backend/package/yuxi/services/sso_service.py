"""SSO (Single Sign-On) 服务模块。

用于与 Java 主系统进行单点登录集成。
Java 系统作为主系统，Python 系统作为从系统。
"""

import os
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from yuxi.repositories.user_repository import UserRepository
from yuxi.storage.postgres.models_business import Department, User
from yuxi.services.java_token_service import java_token_service, JavaTokenData
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

from server.utils.auth_utils import AuthUtils
from server.utils.common_utils import log_operation


class SSOConfig(BaseModel):
    """SSO 配置模型"""

    enabled: bool = Field(default=False, description="是否启用 SSO")
    java_api_base_url: str = Field(default="", description="Java API 基础 URL")
    verify_endpoint: str = Field(default="/api/admin/user/info_out", description="验证用户信息的端点")

    @classmethod
    def from_env(cls) -> "SSOConfig":
        """从环境变量加载配置"""

        def _env(name: str, default: str = "") -> str:
            return os.environ.get(name, default).strip()

        enabled = os.environ.get("SSO_ENABLED", "false").lower() == "true"
        java_api_base_url = _env("SSO_JAVA_API_BASE_URL")

        return cls(
            enabled=enabled,
            java_api_base_url=java_api_base_url,
            verify_endpoint=_env("SSO_VERIFY_ENDPOINT", "/api/admin/user/info_out"),
        )

    def is_configured(self) -> bool:
        """检查 SSO 配置是否完整"""
        if not self.enabled:
            return False
        return bool(self.java_api_base_url)


sso_config = SSOConfig.from_env()


class SSOUserInfo(BaseModel):
    """SSO 用户信息"""

    user_id: str = Field(description="Java 系统的用户 ID")
    username: str = Field(description="用户名")
    name: str = Field(default="", description="姓名")
    avatar: str | None = Field(default=None, description="头像 URL")
    phone: str | None = Field(default=None, description="手机号")
    tenant_id: str | None = Field(default=None, description="租户 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    organization_path: str | None = Field(default=None, description="组织路径")


async def verify_token_with_java_api(tenant_id: str, token: str) -> SSOUserInfo | None:
    """
    调用 Java API 验证 token 并获取用户信息

    Args:
        tenant_id: 租户 ID
        token: 认证 token

    Returns:
        SSOUserInfo: 验证成功返回用户信息，失败返回 None
    """
    if not sso_config.is_configured():
        logger.error("SSO 未正确配置")
        return None

    url = f"{sso_config.java_api_base_url.rstrip('/')}{sso_config.verify_endpoint}"

    headers = {"Tenant-Id": tenant_id, "authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            logger.warning(f"Java API 返回错误: {data.get('msg', 'Unknown error')}")
            return None

        sys_user = data.get("data", {}).get("sysUser", {})
        if not sys_user:
            logger.warning("Java API 返回数据中缺少 sysUser")
            return None

        return SSOUserInfo(
            user_id=sys_user.get("userId", ""),
            username=sys_user.get("username", ""),
            name=sys_user.get("name", ""),
            avatar=sys_user.get("avatar"),
            phone=sys_user.get("phone"),
            tenant_id=sys_user.get("tenantId"),
            organization_id=sys_user.get("organizationId"),
            organization_path=sys_user.get("organizationPath"),
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"Java API HTTP 错误: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Java API 请求错误: {e}")
        return None
    except Exception as e:
        logger.error(f"Java API 调用异常: {e}")
        return None


async def find_user_by_sso_user_id(db, sso_user_id: str) -> User | None:
    """通过 SSO 用户 ID 查找用户"""
    internal_user_id = f"sso:{sso_user_id}"

    result = await db.execute(select(User).filter(User.user_id == internal_user_id, User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user:
        return user

    legacy_result = await db.execute(
        select(User).filter(User.user_id.like(f"{internal_user_id}:%"), User.is_deleted == 0).order_by(User.id.asc())
    )
    legacy_users = list(legacy_result.scalars().all())
    if legacy_users:
        if len(legacy_users) > 1:
            logger.warning(
                f"Multiple legacy SSO users matched for user_id={sso_user_id}, use earliest id={legacy_users[0].id}"
            )
        return legacy_users[0]

    return None


async def find_user_by_username(db, username: str) -> User | None:
    """通过用户名查找用户"""
    result = await db.execute(select(User).filter(User.username == username, User.is_deleted == 0))
    return result.scalar_one_or_none()


async def get_or_create_sso_department(db) -> Department | None:
    """获取或创建 SSO 用户的默认部门"""
    dept_name = "SSO用户"

    result = await db.execute(select(Department).filter(Department.name == dept_name))
    dept = result.scalar_one_or_none()

    if not dept:
        dept = Department(
            name=dept_name,
            description="从主系统单点登录的用户",
        )
        db.add(dept)
        try:
            await db.commit()
            await db.refresh(dept)
            logger.info(f"Created SSO department: {dept_name}")
        except IntegrityError:
            await db.rollback()
            result = await db.execute(select(Department).filter(Department.name == dept_name))
            dept = result.scalar_one_or_none()

    return dept


async def create_sso_user(db, user_info: SSOUserInfo, department_id: int | None = None) -> User:
    """
    创建 SSO 用户

    用户名作为默认密码
    """
    user_repo = UserRepository()

    user_id = user_info.username

    default_password = "1234qwer"  # 默认密码，可以根据需要修改
    password_hash = AuthUtils.hash_password(default_password)

    username = user_info.username

    for retry_index in range(3):
        try:
            new_user = await user_repo.create(
                {
                    "username": username,
                    "user_id": user_id,
                    "phone_number": user_info.phone,
                    "avatar": user_info.avatar,
                    "password_hash": password_hash,
                    "role": "user",
                    "department_id": department_id,
                    "last_login": utc_now_naive(),
                    "require_password_change": 1,
                }
            )
            logger.info(f"Created SSO user: {new_user.username} ({user_id})")
            return new_user
        except IntegrityError:
            existing_user = await find_user_by_username(db, user_info.username)
            if existing_user:
                return existing_user
            username = f"{user_info.username}-{retry_index + 2}"

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="创建 SSO 用户失败，请重试",
    )


async def sso_login_handler(tenant_id: str, token: str, db, request=None) -> dict[str, Any]:
    """
    SSO 登录处理

    Args:
        tenant_id: 租户 ID
        token: 认证 token
        db: 数据库会话
        request: FastAPI Request 对象

    Returns:
        登录响应数据

    Raises:
        HTTPException: 验证失败时抛出
    """
    if not sso_config.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO 登录未配置",
        )

    user_info = await verify_token_with_java_api(tenant_id, token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不是有效用户，请先在主系统中登录",
        )

    user = await find_user_by_username(db, user_info.username)

    if user:
        user.last_login = utc_now_naive()
        if user_info.avatar:
            user.avatar = user_info.avatar
        if user_info.phone:
            user.phone_number = user_info.phone
        if tenant_id:
            user.java_tenant_id = tenant_id
        await db.commit()
        logger.info(f"SSO user logged in: {user.username}")
    else:
        dept = await get_or_create_sso_department(db)
        department_id = dept.id if dept else None
        user = await create_sso_user(db, user_info, department_id)

    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账户已注销",
        )

    token_data = {"sub": str(user.id)}
    jwt_token = AuthUtils.create_access_token(token_data)

    await log_operation(db, user.id, "SSO 登录", request=request)

    department_name = None
    if user.department_id:
        result = await db.execute(select(Department.name).filter(Department.id == user.department_id))
        department_name = result.scalar_one_or_none()

    java_token_status = "valid"
    if user.java_tenant_id:
        java_token_data = JavaTokenData(
            access_token=token,
            refresh_token=None,
            tenant_id=tenant_id,
            tenant_name=user_info.name or user.username,
            created_at=utc_now_naive().isoformat(),
            expires_in=None,
        )
        await java_token_service.save_token(user.id, java_token_data)
        logger.info(f"Java token 已保存到 Redis: user_id={user.id}, tenant_id={tenant_id}")

    # 保存 java_token_status 到 User 表
    user.java_token_status = java_token_status
    await db.commit()

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
        "department_id": user.department_id,
        "department_name": department_name,
        "require_password_change": user.require_password_change,
        "java_token_status": java_token_status,
    }


async def change_sso_user_password(db, user: User, new_password: str) -> None:
    """修改 SSO 用户密码并清除需要修改密码的标记"""
    user.password_hash = AuthUtils.hash_password(new_password)
    user.require_password_change = 0
    await db.commit()
    logger.info(f"SSO user password changed: {user.username}")
