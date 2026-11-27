"""Локальні виміри або фіналізація README після деплою на власний сервіс."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

BASE = "http://127.0.0.1:18078"


def measure(base, count, concurrency):
    url = base + "/search?q=mars&k=5"
    raw = subprocess.check_output(
        [
            os.environ.get("OHA", "oha"),
            "-n",
            str(count),
            "-c",
            str(concurrency),
            "--output-format",
            "json",
            url,
        ]
    )
    data = json.loads(raw)
    if data.get("statusCodeDistribution") != {"200": count}:
        raise RuntimeError(f"Очікувалось {count} успішних запитів")
    percentiles = data["latencyPercentiles"]
    return data["summary"]["total"], [
        data["summary"]["requestsPerSec"],
        *[1000 * percentiles[k] for k in ("p50", "p95", "p99")],
    ]


def wait(base):
    for _ in range(120):
        try:
            with urlopen(base + "/health", timeout=5) as response:
                if json.load(response)["status"] == "ok":
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Сервіс не готовий")


def row(label, numbers):
    return "| " + label + " | " + " | ".join(f"{x:.2f}" for x in numbers) + " |"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        base = sys.argv[1].rstrip("/")
        if urlsplit(base).scheme != "https" or not urlsplit(base).netloc:
            raise SystemExit("Вкажи HTTPS URL власного сервісу")
        wait(base)
        _, values = measure(base, 200, 50)
        readme = Path("README.md")
        lines = readme.read_text().splitlines()
        lines = [
            row("Публічний сервіс", values)
            if s.startswith("| Публічний сервіс |")
            else s
            for s in lines
        ]
        lines = [s for s in lines if not s.startswith("**Публічна адреса:**")]
        lines.insert(1, f"\n**Публічна адреса:** [{base}]({base})")
        readme.write_text("\n".join(lines) + "\n")
    else:
        for label, app, workers in [
            ("async def", "scripts.async_baseline:app", 1),
            ("def", "findex.web.app:app", 1),
            ("def", "findex.web.app:app", 4),
        ]:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    app,
                    "--port",
                    "18078",
                    "--workers",
                    str(workers),
                    "--no-access-log",
                ],
                stdout=subprocess.DEVNULL,
            )
            try:
                wait(BASE)
                measure(BASE, 10, 5)
                wall, _ = measure(BASE, 20, 20)
                print(label, workers, "20 одночасних:", round(wall, 3), "с", flush=True)
                _, values = measure(BASE, 200, 50)
                print(row(f"Локально, {workers} × {label}", values), flush=True)
            finally:
                proc.terminate()
                proc.wait()
