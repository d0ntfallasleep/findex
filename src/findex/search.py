import argparse
import time
import tracemalloc
from pathlib import Path

from findex.query import parse, positive_words
from findex.ranking import BM25, TfIdf, snippet
from findex.ranking import search as ranked_search
from findex.store import load, open_index
from findex.tokenize import tokenize


def merge(left, right, op):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if a == b:
            if op != "NOT":
                result.append(a)
            i += 1
            j += 1
        elif a < b:
            if op != "AND":
                result.append(a)
            i += 1
        else:
            if op == "OR":
                result.append(b)
            j += 1
    if op != "AND":
        result.extend(left[i:])
    if op == "OR":
        result.extend(right[j:])
    return result


def combine(left, right, op, engine):
    if engine == "merge":
        return merge(left, right, op)
    a, b = set(left), set(right)
    if op == "AND":
        return sorted(a & b)
    if op == "OR":
        return sorted(a | b)
    return sorted(a - b)


def search(index, query, engine="merge"):
    # Лише великі AND/OR/NOT є операторами. OR ділить запит на групи.
    parts = []
    for word in query.split():
        if word in ("AND", "OR", "NOT"):
            parts.append(word)
        else:
            parts.extend(tokenize(word))
    if not parts:
        return []
    result = []
    group = None
    negate = False
    need_term = True
    for part in parts:
        if part == "NOT":
            negate = not negate
            need_term = True
            continue
        if part in ("OR", "AND"):
            if need_term:
                raise ValueError("Перед оператором потрібен терм")
            if part == "OR":
                result = combine(result, group, "OR", engine)
                group = None
            need_term = True
            continue
        ids = [p.doc_id for p in index.postings.get(part, [])]
        if negate:
            left = range(len(index.docs)) if group is None else group
            group = combine(left, ids, "NOT", engine)
        elif group is None:
            group = ids
        else:
            group = combine(group, ids, "AND", engine)
        negate = False
        need_term = False
    if need_term:
        raise ValueError("Після оператора потрібен терм")
    return combine(result, group, "OR", engine)


def main():
    parser = argparse.ArgumentParser(description="Boolean-пошук")
    parser.add_argument("index", type=Path)
    parser.add_argument("query")
    parser.add_argument("--engine", choices=["merge", "set"], default=None)
    parser.add_argument("--scorer", choices=("bm25", "tfidf"), default="bm25")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    if args.engine is None:
        scorer = BM25() if args.scorer == "bm25" else TfIdf()
        with open_index(args.index) as ix:
            try:
                results = ranked_search(ix, args.query, scorer, args.top)
                terms = set(positive_words(parse(args.query)))
            except ValueError as error:
                parser.error(str(error))
            for result in results:
                print(f"{result.score:.3f}  {result.title}")
                path = args.data / ix.docs[result.doc_id].path
                if path.is_file():
                    print(
                        snippet(
                            path.read_text(encoding="utf-8"), result.best_term, terms
                        )
                    )
        return
    tracemalloc.start()
    start = time.perf_counter()
    index = load(args.index)
    try:
        hits = search(index, args.query, args.engine)
    except ValueError as error:
        parser.error(str(error))
    elapsed = time.perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1]
    for i in hits:
        doc = index.docs[i]
        print(f"{i:3}  {doc.title}  ({doc.path}, {doc.length} токенів)")
    print(
        f"Знайдено: {len(hits)}. Завантаження і пошук: {elapsed:.4f} с, пік {peak / 2**20:.2f} МіБ"
    )


if __name__ == "__main__":
    main()
