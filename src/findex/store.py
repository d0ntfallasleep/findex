import json
import pickle
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from findex.models import DocMeta, Index, Posting
from findex.timing import timed


def save(index: Index, path: Path) -> None:
    if path.suffix != ".json":
        with path.open("wb") as file:
            pickle.dump(index, file, protocol=pickle.HIGHEST_PROTOCOL)
        return
    data = {
        "docs": [[d.path, d.title, d.length] for d in index.docs],
        "postings": {
            t: [[p.doc_id, p.tf] for p in ps] for t, ps in index.postings.items()
        },
        "positions": index.positions,
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, separators=(",", ":"))


@timed
def load(path: Path) -> Index:
    if path.suffix != ".json":
        # pickle може виконати код під час читання. Відкриваємо лише власний індекс.
        with path.open("rb") as file:
            return pickle.load(file)
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    docs = [DocMeta(*row) for row in data["docs"]]
    postings = {
        t: [Posting(*row) for row in rows] for t, rows in data["postings"].items()
    }
    positions = data["positions"]
    if positions is not None:
        positions = {
            t: {int(i): ps for i, ps in rows.items()} for t, rows in positions.items()
        }
    return Index(postings, docs, positions)


@contextmanager
def open_index(path: Path) -> Generator[Index, None, None]:
    index = load(path)
    try:
        yield index
    finally:
        if "matching" in vars(index):
            index.matching.cache_clear()
