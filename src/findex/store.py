import json
import pickle

from findex.models import DocMeta, Index, Posting


def save(index, path):
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


def load(path):
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
