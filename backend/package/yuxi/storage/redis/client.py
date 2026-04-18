import json
import threading
import redis
from yuxi.config import redis_cfg


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
        password: str | None = None,
        decode_responses: bool = True,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=decode_responses,
        )

        self._client.ping()

        self._initialized = True

    @property
    def raw(self) -> redis.Redis:
        return self._client

    def get(self, key: str):
        return self._client.get(key)

    def set(self, key: str, value, ex: int | None = None):
        return self._client.set(key, value, ex=ex)

    def delete(self, key: str):
        return self._client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def ttl(self, key: str) -> int:
        return self._client.ttl(key)

    def get_json(self, key: str) -> dict | list | None:
        """获取 JSON 格式的数据"""
        data = self._client.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict | list, ex: int | None = None) -> bool:
        """存储 JSON 格式的数据"""
        try:
            data = json.dumps(value, ensure_ascii=False)
            return self._client.set(key, data, ex=ex)
        except (TypeError, json.JSONEncodeError):
            return False

    async def get_json_async(self, key: str) -> dict | list | None:
        """异步获取 JSON 格式的数据"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_json, key)

    async def set_json_async(self, key: str, value: dict | list, ex: int | None = None) -> bool:
        """异步存储 JSON 格式的数据"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set_json, key, value)

    async def delete_async(self, key: str) -> int:
        """异步删除 key"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.delete, key)

    async def exists_async(self, key: str) -> bool:
        """异步检查 key 是否存在"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.exists, key)

    async def ttl_async(self, key: str) -> int:
        """异步获取 key 的剩余 TTL"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.ttl, key)


redis_client = RedisClient(
    host=redis_cfg.REDIS_HOST,
    port=redis_cfg.REDIS_PORT,
    db=redis_cfg.REDIS_DB,
    password=redis_cfg.REDIS_PASSWORD,
)
