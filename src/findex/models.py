from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Posting:
    doc_id: int
    tf: int


@dataclass(frozen=True, slots=True)
class DocMeta:
    path: str
    title: str
    length: int


@dataclass
class Index:
    postings: dict[str, list[Posting]]
    docs: list[DocMeta]
    positions: dict[str, dict[int, list[int]]] | None = None
