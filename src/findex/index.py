import argparse
import time
import tracemalloc
from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import islice
from pathlib import Path

from findex.corpus import Document, iter_documents
from findex.models import DocMeta, Index, Posting
from findex.store import save
from findex.timing import timed
from findex.tokenize import tokenize


@timed
def build_index(root: Path, positions: bool = False, limit: int | None = None) -> Index:
    return build_documents(islice(iter_documents(root), limit), positions)


def build_documents(documents: Iterable[Document], positions: bool) -> Index:
    postings: defaultdict[str, list[Posting]] = defaultdict(list)
    docs: list[DocMeta] = []
    offsets: defaultdict[str, dict[int, list[int]]] | None = (
        defaultdict(dict) if positions else None
    )
    for doc_id, doc in enumerate(documents):
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
