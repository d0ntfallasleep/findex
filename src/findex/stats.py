import argparse
import time
import tracemalloc
from collections import Counter
from collections.abc import Iterable
from itertools import islice
from pathlib import Path

from findex.corpus import Document, iter_documents
from findex.tokenize import tokenize


def lazy_stats(documents: Iterable[Document]) -> tuple[int, Counter[str]]:
    counts = Counter()
    doc_count = 0
    for document in documents:
        doc_count += 1
        counts.update(tokenize(document.text))
    return doc_count, counts


def eager_stats(documents: Iterable[Document]) -> tuple[int, Counter[str]]:
    docs = list(documents)
    token_lists = [list(tokenize(doc.text)) for doc in docs]
    counts = Counter()
    for tokens in token_lists:
        counts.update(tokens)
    return len(docs), counts


def main():
    parser = argparse.ArgumentParser(description="Статистика корпусу текстів")
    parser.add_argument("root", type=Path, help="папка з .txt файлами")
    parser.add_argument("--limit", type=int, help="скільки документів обробити")
    parser.add_argument("--eager", action="store_true", help="використати списки")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"Папку {args.root} не знайдено. Перевір шлях до корпусу.")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit має бути невід’ємним")

    tracemalloc.start()
    start = time.perf_counter()
    documents = islice(iter_documents(args.root), args.limit)
    if args.eager:
        doc_count, counts = eager_stats(documents)
    else:
        doc_count, counts = lazy_stats(documents)
    total = counts.total()
    top = counts.most_common(50)
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Документів: {doc_count}")
    print(f"Токенів: {total}")
    print(f"Різних токенів: {len(counts)}")
    print(f"Час: {elapsed:.3f} с")
    print(f"Пікова пам’ять: {peak / 1024**2:.2f} МіБ")
    print("Топ-50 термів:")
    for term, count in top:
        print(f"{term:18} {count}")


if __name__ == "__main__":
    main()
