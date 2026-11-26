from dataclasses import dataclass
from functools import cached_property, lru_cache


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

    def __len__(self):
        return len(self.postings)

    def __contains__(self, term):
        return term in self.postings

    def __getitem__(self, term):
        return self.postings[term]

    def __iter__(self):
        return iter(self.postings)

    def __repr__(self):
        return f"Index(docs={self.num_docs}, terms={len(self)})"

    @property
    def num_docs(self):
        return len(self.docs)

    @cached_property
    def avg_doc_length(self):
        return sum(d.length for d in self.docs) / self.num_docs if self.docs else 0

    def doc_length(self, doc_id):
        return self.docs[doc_id].length

    def df(self, term):
        return len(self.postings.get(term, ()))

    @cached_property
    def matching(self):
        @lru_cache(maxsize=256)
        def ids(tree):
            return frozenset(tree.evaluate(self))

        return ids

    def __getstate__(self):
        return {key: getattr(self, key) for key in ("docs", "postings", "positions")}
