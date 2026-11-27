import asyncio
import json
import logging
import time
from contextlib import aclosing
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from rich.console import Console
from rich.live import Live

from .crawl import Stats, canonical, crawl
from .fetch import log


async def collect(
    seed: str, cap: int, workers: int, per_host: int, delay: float, out: Path
) -> None:
    seed = canonical(seed)
    if not seed:
        raise ValueError("Потрібен URL http або https")
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = Stats()
    start = time.monotonic()
    handler = logging.FileHandler("crawl.log", encoding="utf-8")
    level = log.level
    log.setLevel(logging.INFO)
    log.propagate = False
    log.addHandler(handler)
    try:
        with (
            out.open("w", encoding="utf-8") as file,
            Live(console=Console(stderr=True), auto_refresh=False) as live,
        ):

            async def display() -> None:
                while True:
                    live.update(
                        f"Сторінок {stats.pages} | {stats.pages / max(0.001, time.monotonic() - start):.1f}/с | очікують {stats.inflight} | помилки {stats.errors} | черга {stats.queued}",
                        refresh=True,
                    )
                    await asyncio.sleep(0.1)

            async with asyncio.TaskGroup() as group:
                progress = group.create_task(display())
                try:
                    async with aclosing(
                        crawl(
                            [seed],
                            max_pages=cap,
                            concurrency=workers,
                            per_host=per_host,
                            delay=delay,
                            allowed_domains={urlsplit(seed).netloc},
                            stats=stats,
                        )
                    ) as pages:
                        async for page in pages:
                            await asyncio.to_thread(
                                file.write,
                                json.dumps(asdict(page), ensure_ascii=False) + "\n",
                            )
                            await asyncio.to_thread(file.flush)
                finally:
                    progress.cancel()
            live.update(
                f"Зібрано {stats.pages} | {stats.pages / (time.monotonic() - start):.1f}/с | очікують {stats.inflight} | помилки {stats.errors} | черга {stats.queued}",
                refresh=True,
            )
    finally:
        log.removeHandler(handler)
        handler.close()
        log.setLevel(level)
        log.propagate = True
