"""Власне локальне дзеркало. Запуск: uv run python scripts/bench_lab06.py."""

import asyncio
import os
import resource
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from findex.crawler.command import collect

SEED = "http://127.0.0.1:18766/"


class Mirror(BaseHTTPRequestHandler):
    busy = True

    def do_GET(self):
        time.sleep(0.025)
        status = 200
        if self.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /private"
        elif self.path == "/":
            body = "".join(f'<a href="/{i}">Chapter {i}</a>' for i in range(1, 200))
        elif self.path == "/1" and Mirror.busy:
            Mirror.busy = False
            status = 429
            body = "Please retry"
        else:
            body = f"<title>Chapter {self.path[1:]}</title><p>Mars and Earth</p>"
        self.send_response(status)
        self.send_header(
            "Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html"
        )
        if status == 429:
            self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if sys.argv[1:] == ["--serve"]:
        with ThreadingHTTPServer(("127.0.0.1", 18766), Mirror) as server:
            print("Локальне дзеркало:", SEED, flush=True)
            server.serve_forever()
        sys.exit(0)
    if len(sys.argv) > 1:
        start = time.perf_counter()
        asyncio.run(collect(SEED, 200, int(sys.argv[1]), 5, 0.002, Path("pages.jsonl")))
        wall = time.perf_counter() - start
        with Path("pages.jsonl").open() as stream:
            pages = sum(1 for _ in stream)
        assert pages == 200
        lines = Path("crawl.log").read_text().splitlines()
        failures = sum("status=429 " in line for line in lines)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
            1024**2 if sys.platform == "darwin" else 1024
        )
        print(
            f"| {sys.argv[1]} | {pages} | {wall:.3f} | {pages / wall:.2f} | {failures} | {200 - pages} | {rss:.2f} |"
        )
    else:
        with ThreadingHTTPServer(("127.0.0.1", 18766), Mirror) as server:
            Thread(target=server.serve_forever, daemon=True).start()
            for n in (1, 5, 20):
                Mirror.busy = True
                with tempfile.TemporaryDirectory() as folder:
                    subprocess.run(
                        [sys.executable, str(Path(__file__).resolve()), str(n)],
                        cwd=folder,
                        check=True,
                        env={**os.environ, "PYTHONASYNCIODEBUG": "1"},
                    )
                    if n == 20:
                        print("\n```text")
                        for line in Path(folder, "crawl.log").read_text().splitlines():
                            if line.startswith(SEED + "1 "):
                                print(line)
                        print("```")
            server.shutdown()
