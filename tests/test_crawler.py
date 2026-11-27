import asyncio
import json
from collections import Counter
from contextlib import aclosing

import httpx
import pytest

from findex.crawler.crawl import canonical, crawl
from findex.crawler.fetch import fetch, retry_after
from findex.index import build_index


@pytest.mark.parametrize("code,count", [(404, 1), (403, 1), (429, 4), (503, 4)])
def test_fetch(code, count, monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    calls = []

    def handle(request):
        calls.append(request.url)
        return httpx.Response(code, headers={"Retry-After": "2"}, text="err")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await fetch(client, "http://mirror/page")
            assert (result.status, result.size) == (code, 3)

    asyncio.run(run())
    assert len(calls) == count and delays == [2] * (count - 1)


def test_timeout():
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            await asyncio.sleep(0.1)
        return httpx.Response(200)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await fetch(client, "https://test/", timeout=0.02)).status == 200

    asyncio.run(run())
    assert len(calls) == 2


def test_canonical():
    assert (
        canonical("HTTPS://EXAMPLE.org/abc/?z=2&a=1#x")
        == "https://example.org/abc?a=1&z=2"
    )
    assert retry_after("Thu, 01 Jan 1970 00:00:00 GMT") == 0


@pytest.mark.parametrize("cap,early", [(1, False), (10, False), (10, True)])
def test_frontier(cap, early):
    calls = Counter()

    def handle(request):
        path = request.url.path
        calls[path] += 1
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        html = '<a href="/x/">x</a><a href="/x#other">x</a><a href="/private">p</a><a href="https://outside.org">z</a>'
        assert request.url.host == "test"
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})

    async def run():
        result = []
        async with aclosing(
            crawl(
                ["https://test"],
                concurrency=5,
                per_host=2,
                max_pages=cap,
                delay=0,
                allowed_domains={"test"},
                transport=httpx.MockTransport(handle),
            )
        ) as stream:
            async for page in stream:
                result.append(page)
                if early:
                    break
        return result

    pages = asyncio.run(run())
    assert len(pages) == (1 if early or cap == 1 else 2)
    assert (
        calls["/robots.txt"] == 1
        and calls["/private"] == 0
        and max(calls.values()) == 1
    )


def test_jsonl_index(tmp_path):
    path = tmp_path / "crawl.jsonl"
    path.write_text(
        json.dumps({"url": "https://test/", "title": "Mars", "text": "red mars"})
        + "\n",
        encoding="utf-8",
    )
    ix = build_index(path, positions=True)
    assert ix["mars"][0].tf == 2 and ix.docs[0].path == "https://test/"
