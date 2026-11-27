import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .fetch import FetchResult


class RobotsCache:
    def __init__(self, get: Callable[[str], Awaitable[FetchResult]]) -> None:
        self.get = get
        self.rules: dict[str, RobotFileParser] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self.locks.setdefault(origin, asyncio.Lock()):
            if origin not in self.rules:
                result = await self.get(origin + "/robots.txt")
                rules = RobotFileParser()
                if result.status == 200 and result.response is not None:
                    rules.parse(result.response.text.splitlines())
                elif result.status in (404, 410):
                    rules.parse(["User-agent: *", "Disallow:"])
                else:
                    rules.parse(["User-agent: *", "Disallow: /"])
                self.rules[origin] = rules
        return self.rules[origin].can_fetch("findex", url)
