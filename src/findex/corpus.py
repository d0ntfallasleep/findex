import logging
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Document(NamedTuple):
    doc_id: str
    path: Path
    text: str


def iter_documents(root: Path) -> Iterator[Document]:
    for path in root.rglob("*.txt"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            logger.warning("Пропускаю %s (%s)", path, error)
            continue

        yield Document(path.relative_to(root).as_posix(), path, text)
