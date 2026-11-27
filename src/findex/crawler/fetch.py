import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

log = logging.getLogger("findex.crawl")
AGENT = "findex/0.6 (+https://github.com/d0ntfallasleep/findex/issues)"


@dataclass
class FetchResult:
    response: httpx.Response | None
    status: int
    size: int
    elapsed: float


def retry_after(value: str) -> float:
    if value.isdigit():
        return float(value)
    try:
        return max(0, parsedate_to_datetime(value).timestamp() - time.time())
    except (ValueError, TypeError, OverflowError):
        return 0


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 10,
    request: Callable[[str], Awaitable[httpx.Response]] | None = None,
) -> FetchResult:
    for attempt in range(4):
        start = time.monotonic()
        response = None
        try:
            if request is None:
                async with asyncio.timeout(timeout):
                    response = await client.get(url)
            else:
                response = await request(url)
            status = response.status_code
            again = status == 429 or 500 <= status < 600
        except (TimeoutError, httpx.TimeoutException):
            status, again = 0, True
        except httpx.RequestError:
            status, again = 0, False
        result = FetchResult(
            response,
            status,
            len(response.content) if response is not None else 0,
            time.monotonic() - start,
        )
        log.info(
            "%s status=%s bytes=%d elapsed=%.4f attempt=%d",
            url,
            status,
            result.size,
            result.elapsed,
            attempt + 1,
        )
        if not again or attempt == 3:
            return result
        delay = 0.1 * 2**attempt + random.uniform(0, 0.05)
        if response is not None:
            delay = max(delay, retry_after(response.headers.get("retry-after", "")))
        await asyncio.sleep(delay)
    raise AssertionError("unreachable")
