import threading
import redis
from typing import Optional
from src.config import redis_cfg


class RedisClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True,
    ):
        # 防止 __init__ 被多次执行
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=decode_responses,
        )

        # 健康检查
        self._client.ping()

        self._initialized = True

    @property
    def raw(self) -> redis.Redis:
        return self._client

    # ===== 常用方法 =====

    def get(self, key: str):
        return self._client.get(key)

    def set(self, key: str, value, ex: Optional[int] = None):
        return self._client.set(key, value, ex=ex)

    def delete(self, key: str):
        return self._client.delete(key)


redis_client = RedisClient(
    host=redis_cfg.REDIS_HOST,
    port=redis_cfg.REDIS_PORT,
    db=redis_cfg.REDIS_DB,
    password=redis_cfg.REDIS_PASSWORD,
)
