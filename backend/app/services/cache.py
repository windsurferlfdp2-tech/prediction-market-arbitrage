from redis.asyncio import Redis

from app.config import Settings


class RedisCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    async def ping(self) -> bool:
        return bool(await self.client.ping())
