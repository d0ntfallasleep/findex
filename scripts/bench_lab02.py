"""Замір на поточному data/ та оновлення секції лабораторної 2 у README."""

import gc
import pickle
import platform
import time
import tracemalloc
from array import array
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from timeit import repeat

from findex.index import build_index
from findex.models import Posting
from findex.search import search
from findex.store import load, save


@dataclass(frozen=True)
class PlainPosting:
    doc_id: int
    tf: int


def memory(rows, kind):
    gc.collect()
    tracemalloc.start()
    table = {}
    for term, pairs in rows.items():
        if kind == "array":
            ids, freqs = array("I"), array("I")
            for i, tf in pairs:
                ids.append(i)
                freqs.append(tf)
            table[term] = (ids, freqs)
        else:
            cls = PlainPosting if kind == "dataclass" else Posting
            table[term] = [cls(i, tf) for i, tf in pairs]
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    raw = pickle.dumps(table, protocol=pickle.HIGHEST_PROTOCOL)
    start = time.perf_counter()
    restored = pickle.loads(raw)
    elapsed = time.perf_counter() - start
    assert restored == table
    return peak, len(raw), elapsed * 1000


def main():
    root = Path("data")
    idx = build_index(root)
    if len(idx.postings) < 4:
        raise SystemExit("Спочатку виконай uv run python scripts/prepare_data.py")
    report = [
        "## Лабораторна 2. Інвертований індекс",
        "",
        (
            "З кожного розділу беру слова через tokenize(). Counter рахує повтори всередині "
            "розділу. Для кожного терма додаю в defaultdict один постінг з номером документа "
            "та частотою. Номери видаються послідовно, тому списки одразу відсортовані. "
            "У DocMeta зберігаю шлях, заголовок і довжину в токенах."
        ),
        "",
        "```bash",
        "uv run python -m findex.index data/ --out index.bin",
        'uv run python -m findex.search index.bin "mars NOT earth" --engine merge',
        'uv run python -m findex.search index.bin "mars OR earth" --engine set',
        "uv run python -m findex.index data/ --out index.json --positions",
        "```",
        "",
        (
            "Пробіл або AND означає перетин, OR — об’єднання, NOT — виключення. "
            "Оператори пишуться великими літерами. Спочатку обчислюється NOT, потім AND, потім OR. "
            "Дужки не підтримуються. Нумерація позицій токенів починається з нуля."
        ),
        "",
        (
            f"Вимірювання: Python {platform.python_version()}, {platform.system()}, "
            f"{len(idx.docs)} документів, {len(idx.postings)} термів, "
            f"{sum(d.length for d in idx.docs)} токенів."
        ),
        "",
        "### Пам’ять постінгів",
        "",
        "| Представлення | Пік, байт | Pickle постінгів, байт | Декодування, мс |",
        "|---|---:|---:|---:|",
    ]
    rows = {t: [(p.doc_id, p.tf) for p in ps] for t, ps in idx.postings.items()}
    for kind in ("dataclass", "slots", "array"):
        peak, size, ms = memory(rows, kind)
        report.append(f"| {kind} | {peak} | {size} | {ms:.2f} |")
    report.extend(
        [
            "",
            (
                "Вхідні пари підготовлено до запуску tracemalloc. "
                "Таблиця показує додаткову пам’ять для побудови словника постінгів. "
                "Звичайний dataclass зберігає атрибути в словнику екземпляра. "
                "slots прибирає цей словник. Два масиви на терм зберігають числа "
                "підряд, але для коротких списків заголовки масивів теж займають місце."
            ),
            "",
            "### Пошук",
            "",
            (
                "Дві пари вибрано за сумою частот по корпусу. При рівності беру "
                "терми за абеткою. Час включає розбір запиту, без читання індексу. "
                "Медіана п’яти серій по 1000 пошуків."
            ),
            "",
            "| Запит AND | Збіги | merge, мкс | set, мкс |",
            "|---|---:|---:|---:|",
        ]
    )
    totals = {t: sum(p.tf for p in ps) for t, ps in idx.postings.items()}
    for sign in (-1, 1):
        terms = sorted(totals, key=lambda t: (sign * totals[t], t))[:2]
        query = " ".join(terms)
        hits = search(idx, query)
        assert hits == search(idx, query, "set")
        times = []
        for engine in ("merge", "set"):
            samples = repeat(partial(search, idx, query, engine), number=1000, repeat=5)
            times.append(median(samples) * 1000)
        report.append(f"| {query} | {len(hits)} | {times[0]:.2f} | {times[1]:.2f} |")
    report.extend(
        [
            "",
            "### Збереження і завантаження",
            "",
            "| Формат | Позиції | Байт | Запис, мс | Читання, мс |",
            "|---|---|---:|---:|---:|",
        ]
    )
    with TemporaryDirectory() as folder:
        for positions in (False, True):
            index = build_index(root, True) if positions else idx
            for ext in ("bin", "json"):
                path = Path(folder) / ("index." + ext)
                start = time.perf_counter()
                save(index, path)
                written = time.perf_counter()
                restored = load(path)
                loaded = time.perf_counter()
                assert restored == index
                fmt = "pickle" if ext == "bin" else "JSON"
                report.append(
                    f"| {fmt} | {'так' if positions else 'ні'} | "
                    f"{path.stat().st_size} | {(written - start) * 1000:.2f} | "
                    f"{(loaded - written) * 1000:.2f} |"
                )
    report.extend(
        [
            "",
            (
                "Позиції додають список місць входження для кожної пари терм–документ. "
                "Pickle читаю лише з власних файлів: під час відновлення об’єкта він може "
                "виконати сторонній код. JSON зберігає звичайні числа, списки й рядки."
            ),
            "",
            "Повторити заміри: `uv run python scripts/bench_lab02.py`.",
        ]
    )
    file = Path("README.md")
    start_marker = "<!-- lab-02:start -->"
    end_marker = "<!-- lab-02:end -->"
    text = file.read_text(encoding="utf-8")
    block = start_marker + "\n" + "\n".join(report) + "\n" + end_marker
    if start_marker in text:
        before, _, old = text.partition(start_marker)
        _, marker, after = old.partition(end_marker)
        if not marker:
            raise SystemExit("Незакритий блок lab-02 у README")
        text = before + block + after
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    file.write_text(text, encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
