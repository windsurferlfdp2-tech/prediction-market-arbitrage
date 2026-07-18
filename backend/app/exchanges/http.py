import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
import structlog


log = structlog.get_logger()


class RetryingHttpClient:
    def __init__(self, timeout_seconds: float, retries: int, backoff_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds

    async def get_json(
        self, url: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(self.retries + 1):
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    log.info("exchange_request_ok", url=url, attempt=attempt)
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("expected JSON object")
                    return data
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    log.warning("exchange_request_failed", url=url, attempt=attempt, error=str(exc))
                    if attempt < self.retries:
                        await asyncio.sleep(self.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error
