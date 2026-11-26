import logging
import re
from dataclasses import dataclass, field
from heapq import nlargest
from math import log, log1p
from typing import Protocol

from findex.models import Index, Posting
from findex.query import parse, positive_words
from findex.timing import timed
from findex.tokenize import tokenize


class Scorer(Protocol):
    def score(self, term: str, posting: Posting, index: Index) -> float: ...


class TfIdf:
    def score(self, term: str, posting: Posting, index: Index) -> float:
        idf = 1 + log((1 + index.num_docs) / (1 + index.df(term)))
        return (1 + log(posting.tf)) * idf


@dataclass(frozen=True)
class BM25:
    k1: float = 1.5
    b: float = 0.75

    def score(self, term: str, posting: Posting, index: Index) -> float:
        df = index.df(term)
        idf = log1p((index.num_docs - df + 0.5) / (df + 0.5))
        ratio = index.doc_length(posting.doc_id) / index.avg_doc_length
        norm = self.k1 * (1 - self.b + self.b * ratio)
        return idf * posting.tf * (self.k1 + 1) / (posting.tf + norm)


@dataclass(order=True, frozen=True)
class SearchResult:
    score: float
    doc_id: int
    title: str = field(compare=False)
    best_term: str = field(compare=False)


@timed
def search(
    index: Index, query: str, scorer: Scorer = BM25(), k: int = 10
) -> list[SearchResult]:
    tree = parse(query)
    before = index.matching.cache_info().hits
    ids = index.matching(tree)
    hit = index.matching.cache_info().hits > before
    logging.getLogger(__name__).debug(f"cache {'hit' if hit else 'miss'}: {query}")
    scores: dict[int, float] = {}
    best: dict[int, tuple[float, str]] = {}
    for word in dict.fromkeys(positive_words(tree)):
        for posting in index.postings.get(word, ()):
            i = posting.doc_id
            if i in ids:
                value = scorer.score(word, posting, index)
                scores[i] = scores.get(i, 0.0) + value
                if i not in best or value > best[i][0]:
                    best[i] = (value, word)
    results = (
        SearchResult(
            scores.get(i, 0.0), i, index.docs[i].title, best.get(i, (0, ""))[1]
        )
        for i in ids
    )
    return nlargest(k, results)


def snippet(text: str, best: str, terms: set[str]) -> str:
    words: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\W_]+(?:['’ʼ][^\W_]+)*", text):
        word = next(tokenize(match.group()), "")
        if word in terms:
            words.append((match.start(), match.end(), word))
    start, end = next(((a, b) for a, b, w in words if w == best), (0, 0))
    left, right = max(0, start - 80), min(len(text), end + 80)
    chunk = text[left:right]
    for a, b, _ in reversed(words):
        if left <= a and b <= right:
            chunk = (
                chunk[: a - left]
                + "**"
                + chunk[a - left : b - left]
                + "**"
                + chunk[b - left :]
            )
    return " ".join(chunk.split())
