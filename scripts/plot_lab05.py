# /// script
# dependencies = ["matplotlib"]
# ///
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    fig, (actual, ideal) = plt.subplots(1, 2, figsize=(10, 4), width_ratios=[2, 1])
    for filename, mode, label in [
        ("gil", "threads", "Потоки, GIL"),
        ("gil", "processes", "Процеси, GIL"),
        ("free", "threads", "Потоки, без GIL"),
    ]:
        with Path(f"docs/{filename}.csv").open() as file:
            rows = [r for r in csv.DictReader(file) if r["executor"] == mode]
        x = [int(r["workers"]) for r in rows]
        y = [float(r["speedup"]) for r in rows]
        for ax in (actual, ideal):
            ax.plot(x, y, marker="o", label=label)
    ideal.plot(x, x, "k--", label="Ідеально: S=N")
    actual.axhline(1, color="gray", linestyle=":")
    for ax in (actual, ideal):
        ax.set_xlabel("Воркери")
        ax.set_xticks(x)
        ax.grid(alpha=0.2)
    actual.set_ylabel("Прискорення до serial своєї збірки")
    actual.set_title("Виміряні значення")
    ideal.set_title("Лінійний орієнтир")
    ideal.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig("docs/lab05-speedup.png", dpi=160)


if __name__ == "__main__":
    main()
