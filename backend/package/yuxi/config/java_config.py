import os

from pydantic import Field
from pydantic_settings import BaseSettings


class JavaConfig(BaseSettings):
    """
    Java 系统集成配置
    """

    enabled: bool = Field(
        description="是否启用 Java API 访问",
        default=os.environ.get("JAVA_ACCESS", "true").lower() == "true",
    )

    api_base_url: str = Field(
        description="Java API 基础地址",
        default=os.environ.get("JAVA_API_BASE_URL") or "http://8.130.128.22/api",
    )

    token_ttl: int = Field(
        description="Token 默认 TTL（秒）",
        default=int(os.environ.get("JAVA_TOKEN_TTL") or 86400),
    )

    def get_login_url(self) -> str:
        """获取 Java 系统登录页面 URL"""
        base_url = self.api_base_url.replace("/api", "").rstrip("/")
        return f"{base_url}"

    def is_configured(self) -> bool:
        """检查配置是否完整"""
        if not self.enabled:
            return False
        return bool(self.api_base_url)


java_config = JavaConfig()
