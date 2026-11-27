"""Запускати з кореня проєкту. Бенчмарк використовує тільки стандартну бібліотеку."""

import csv
import json
import os
import resource
import subprocess
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

from findex.index import build_index


def cpu():
    parent, children = (
        resource.getrusage(who)
        for who in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)
    )
    return parent.ru_utime + parent.ru_stime + children.ru_utime + children.ru_stime


def once(mode, workers):
    times = []
    start_cpu = cpu()
    start = perf_counter()
    index = build_index(
        Path("data"), True, workers=workers, executor=mode, merge_timer=times.append
    )
    wall = perf_counter() - start
    used_cpu = cpu() - start_cpu
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if not index.docs:
        raise ValueError("Порожній корпус")
    return [
        wall,
        used_cpu,
        rss / (1024**2 if sys.platform == "darwin" else 1024),
        times[0],
    ]


if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(json.dumps(once(sys.argv[1], int(sys.argv[2]))))
    else:
        gil = sys._is_gil_enabled()
        modes = ["serial", "threads", "processes"] if gil else ["serial", "threads"]
        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "GIL",
                "executor",
                "workers",
                "wall_s",
                "cpu_s",
                "rss_MiB",
                "merge_s",
                "speedup",
            ]
        )
        for mode in modes:
            for n in (
                [1] if mode == "serial" else sorted({1, 2, 4, 8, os.cpu_count() or 1})
            ):
                samples = [
                    json.loads(
                        subprocess.check_output(
                            [sys.executable, __file__, mode, str(n)]
                        )
                    )
                    for _ in range(3)
                ]
                values = [median(x) for x in zip(*samples, strict=True)]
                if mode == "serial":
                    baseline = values[0]
                writer.writerow(
                    [
                        gil,
                        mode,
                        n,
                        *[round(x, 6) for x in values],
                        round(baseline / values[0], 4),
                    ]
                )
                sys.stdout.flush()
