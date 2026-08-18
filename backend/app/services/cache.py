from typing import Protocol

from redis.asyncio import Redis

from app.config import Settings


class CacheBackend(Protocol):
    async def ping(self) -> bool: ...

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, expire_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self._values.get(key)

    async def set(self, key: str, value: str, expire_seconds: int | None = None) -> None:
        del expire_seconds
        self._values[key] = value

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)


class RedisCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    async def get(self, key: str) -> str | None:
        value = await self.client.get(key)
        if value is None or isinstance(value, str):
            return value
        return str(value)

    async def set(self, key: str, value: str, expire_seconds: int | None = None) -> None:
        await self.client.set(key, value, ex=expire_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)


def create_cache_backend(settings: Settings) -> CacheBackend:
    if settings.local_development:
        return InMemoryCache()
    return RedisCache(settings)
