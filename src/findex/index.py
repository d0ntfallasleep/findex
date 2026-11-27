import argparse
import multiprocessing
import time
import tracemalloc
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Literal

from findex.corpus import Document, read_documents
from findex.models import DocMeta, Index, Posting
from findex.store import save
from findex.timing import timed
from findex.tokenize import tokenize

type Executor = Literal["serial", "threads", "processes"]


@dataclass
class Chunk:
    root: Path
    paths: list[Path]
    start: int
    positions: bool


def build_partial(chunk: Chunk) -> Index:
    try:
        return build_documents(
            read_documents(chunk.root, chunk.paths), chunk.positions, chunk.start
        )
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            f"Помилка воркера, діапазон починається з {chunk.start}"
        ) from exc


def merge(chunks: list[Chunk], partials: list[Index], positions: bool) -> Index:
    result = Index({}, [], {} if positions else None)
    for chunk, partial in zip(chunks, partials, strict=True):
        # Пошкоджені файли пропускаються. Прибираємо можливі проміжки між діапазонами.
        shift = chunk.start - len(result.docs)
        result.docs.extend(partial.docs)
        for term, postings in partial.postings.items():
            target = result.postings.setdefault(term, [])
            if shift:
                target.extend(Posting(p.doc_id - shift, p.tf) for p in postings)
            else:
                target.extend(postings)
        if result.positions is not None and partial.positions is not None:
            for term, offsets in partial.positions.items():
                result.positions.setdefault(term, {}).update(
                    {i - shift: ps for i, ps in offsets.items()}
                )
    return result


@timed
def build_index(
    root: Path,
    positions: bool = False,
    limit: int | None = None,
    workers: int = 1,
    executor: Executor = "serial",
    merge_timer: Callable[[float], None] | None = None,
) -> Index:
    if workers < 1:
        raise ValueError("workers має бути додатним")
    paths = root.rglob("*.txt")
    batch = list(islice(paths, limit))
    chunks: list[Chunk] = []
    partials: list[Index] = []
    processed = 0
    valid = 0
    while batch:
        count = 1 if executor == "serial" else min(workers, len(batch))
        jobs = [
            Chunk(
                root,
                batch[i * len(batch) // count : (i + 1) * len(batch) // count],
                processed + i * len(batch) // count,
                positions,
            )
            for i in range(count)
        ]
        if executor == "serial":
            ready = [build_partial(job) for job in jobs]
        elif executor == "threads":
            with ThreadPoolExecutor(count) as pool:
                ready = list(pool.map(build_partial, jobs))
        else:
            with ProcessPoolExecutor(
                count, mp_context=multiprocessing.get_context("spawn")
            ) as processes:
                ready = list(processes.map(build_partial, jobs))
        chunks.extend(jobs)
        partials.extend(ready)
        valid += sum(len(p.docs) for p in ready)
        processed += len(batch)
        batch = (
            list(islice(paths, limit - valid))
            if limit is not None and valid < limit
            else []
        )
    start = time.perf_counter()
    result = merge(chunks, partials, positions)
    if merge_timer is not None:
        merge_timer(time.perf_counter() - start)
    return result


def build_documents(
    documents: Iterable[Document], positions: bool, start: int = 0
) -> Index:
    postings: defaultdict[str, list[Posting]] = defaultdict(list)
    docs: list[DocMeta] = []
    offsets: defaultdict[str, dict[int, list[int]]] | None = (
        defaultdict(dict) if positions else None
    )
    for doc_id, doc in enumerate(documents, start):
        counts: Counter[str] = Counter()
        for pos, term in enumerate(tokenize(doc.text)):
            counts[term] += 1
            if offsets is not None:
                offsets[term].setdefault(doc_id, []).append(pos)
        for term, tf in counts.items():
            postings[term].append(Posting(doc_id, tf))
        title = doc.text.partition("\n")[0].strip() or doc.path.stem
        docs.append(DocMeta(doc.doc_id, title, counts.total()))
    return Index(dict(postings), docs, dict(offsets) if offsets is not None else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Побудова інвертованого індексу")
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--positions", action="store_true")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("Папку корпусу не знайдено")
    tracemalloc.start()
    start = time.perf_counter()
    index = build_index(args.root, args.positions)
    save(index, args.out)
    peak = tracemalloc.get_traced_memory()[1]
    print(f"{len(index.docs)} документів, {len(index.postings)} термів")
    print(
        f"Побудова і запис: {time.perf_counter() - start:.3f} с, пік {peak / 2**20:.2f} МіБ"
    )


if __name__ == "__main__":
    main()
