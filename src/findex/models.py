from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from findex.query import Node
from dataclasses import dataclass
from functools import cached_property, lru_cache


class CacheInfo(Protocol):
    @property
    def hits(self) -> int: ...


class MatchCache(Protocol):
    def __call__(self, tree: Node, /) -> frozenset[int]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...


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

    def __len__(self) -> int:
        return len(self.postings)

    def __contains__(self, term: str) -> bool:
        return term in self.postings

    def __getitem__(self, term: str) -> list[Posting]:
        return self.postings[term]

    def __iter__(self) -> Iterator[str]:
        return iter(self.postings)

    def __repr__(self) -> str:
        return f"Index(docs={self.num_docs}, terms={len(self)})"

    @property
    def num_docs(self) -> int:
        return len(self.docs)

    @cached_property
    def avg_doc_length(self) -> float:
        return sum(d.length for d in self.docs) / self.num_docs if self.docs else 0

    def doc_length(self, doc_id: int) -> int:
        return self.docs[doc_id].length

    def df(self, term: str) -> int:
        return len(self.postings.get(term, ()))

    @cached_property
    def matching(self) -> MatchCache:
        @lru_cache(maxsize=256)
        def ids(tree: Node) -> frozenset[int]:
            return frozenset(tree.evaluate(self))

        return ids

    def __getstate__(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in ("docs", "postings", "positions")}
