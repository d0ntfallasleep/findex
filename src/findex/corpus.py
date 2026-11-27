import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Document(NamedTuple):
    doc_id: str
    path: Path
    text: str


def read_documents(root: Path, paths: Iterable[Path]) -> Iterator[Document]:
    for path in paths:
        if path.suffix == ".jsonl":
            yield from json_documents(path)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            logger.warning("Пропускаю %s (%s)", path, error)
            continue

        yield Document(path.relative_to(root).as_posix(), path, text)


def iter_documents(root: Path) -> Iterator[Document]:
    yield from read_documents(root, corpus_paths(root))


def json_documents(path: Path) -> Iterator[Document]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            yield Document(row["url"], path, row["title"] + "\n" + row["text"])


def corpus_paths(root: Path) -> Iterator[Path]:
    if root.is_file():
        yield root
    else:
        yield from root.rglob("*.txt")
        yield from root.rglob("*.jsonl")
