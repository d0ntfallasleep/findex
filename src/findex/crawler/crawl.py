import asyncio
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .fetch import AGENT, FetchResult, fetch, log
from .robots import RobotsCache


def canonical(url: str) -> str:
    try:
        p = urlsplit(url)
        if (
            p.scheme not in ("http", "https")
            or not p.hostname
            or p.username
            or p.password
        ):
            return ""
        _ = p.port
        return urlunsplit(
            (
                p.scheme.lower(),
                p.netloc.lower(),
                p.path.rstrip("/") or "/",
                urlencode(sorted(parse_qsl(p.query, keep_blank_values=True))),
                "",
            )
        )
    except ValueError:
        return ""


class HTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.words: list[str] = []
        self.title: list[str] = []
        self.in_title = False
        self.hidden = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.append(dict(attrs).get("href") or "")
        if tag == "title":
            self.in_title = True
        if tag in ("style", "script"):
            self.hidden = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in ("style", "script"):
            self.hidden = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title.append(data)
        elif not self.hidden and data.strip():
            self.words.append(data.strip())


@dataclass
class Page:
    url: str
    title: str
    text: str
    fetched_at: str


@dataclass
class Stats:
    pages: int = 0
    inflight: int = 0
    errors: int = 0
    queued: int = 0


async def crawl(
    seeds: list[str],
    *,
    max_pages: int,
    concurrency: int,
    per_host: int,
    allowed_domains: set[str],
    delay: float = 0.05,
    stats: Stats | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncGenerator[Page, None]:
    if min(concurrency, per_host, max_pages) < 1 or delay < 0:
        raise ValueError("Некоректні ліміти обходу")
    state = stats if stats is not None else Stats()
    frontier: asyncio.Queue[str] = asyncio.Queue()
    jobs: asyncio.Queue[str] = asyncio.Queue()
    done: asyncio.Queue[tuple[Page | None, list[str]]] = asyncio.Queue()
    seen: set[str] = set()

    def enqueue(url: str) -> None:
        url = canonical(url)
        if url and urlsplit(url).netloc in allowed_domains and url not in seen:
            seen.add(url)
            frontier.put_nowait(url)

    for seed in seeds:
        enqueue(seed)
    global_limit = asyncio.Semaphore(concurrency)
    hosts: dict[str, asyncio.Semaphore] = {}
    locks: dict[str, asyncio.Lock] = {}
    last: dict[str, float] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": AGENT}, transport=transport, trust_env=False
    ) as client:

        async def request(url: str) -> httpx.Response:
            host = urlsplit(url).netloc
            async with (
                hosts.setdefault(host, asyncio.Semaphore(per_host)),
                global_limit,
            ):
                async with locks.setdefault(host, asyncio.Lock()):
                    await asyncio.sleep(
                        max(0, last.get(host, 0) + delay - time.monotonic())
                    )
                    last[host] = time.monotonic()
                state.inflight += 1
                try:
                    async with asyncio.timeout(10):
                        return await client.get(url)
                finally:
                    state.inflight -= 1

        async def get(url: str) -> FetchResult:
            return await fetch(client, url, request=request)

        robots = RobotsCache(get)

        async def worker() -> None:
            while True:
                url = await jobs.get()
                page = None
                links: list[str] = []
                if await robots.allowed(url):
                    r = await get(url)
                    if r.status == 200 and r.response is not None:
                        if (
                            "text/html"
                            in r.response.headers.get("content-type", "").lower()
                        ):
                            html = HTML()
                            await asyncio.to_thread(html.feed, r.response.text)
                            page = Page(
                                url,
                                " ".join(html.title),
                                " ".join(html.words),
                                datetime.now(UTC).isoformat(),
                            )
                            links = [
                                urljoin(str(r.response.url), link)
                                for link in html.links
                            ]
                    else:
                        state.errors += 1
                else:
                    log.info("%s robots=denied", url)
                await done.put((page, links))

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(worker()) for _ in range(concurrency)]
            active = 0
            try:
                while state.pages < max_pages:
                    while (
                        active < min(concurrency, max_pages - state.pages)
                        and not frontier.empty()
                    ):
                        jobs.put_nowait(frontier.get_nowait())
                        active += 1
                    state.queued = frontier.qsize()
                    if not active:
                        break
                    page, links = await done.get()
                    active -= 1
                    for link in links:
                        enqueue(link)
                    if page:
                        state.pages += 1
                        yield page
            except GeneratorExit:
                return
            finally:
                for task in tasks:
                    task.cancel()
