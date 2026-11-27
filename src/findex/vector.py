from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import log, log1p
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from findex.models import Index
from findex.query import parse, positive_words
from findex.ranking import BM25, SearchResult, TfIdf

type Ints = NDArray[np.int32]


@dataclass
class Packed:
    spans: dict[str, tuple[int, int]]
    ids: Ints
    tfs: Ints
    lengths: Ints

    @classmethod
    def build(cls, ix: Index) -> Packed:
        n = sum(len(ps) for ps in ix.postings.values())
        ids = np.empty(n, dtype=np.int32)
        tfs = np.empty_like(ids)
        spans: dict[str, tuple[int, int]] = {}
        end = 0
        for term, ps in ix.postings.items():
            start = end
            end += len(ps)
            spans[term] = (start, end)
            ids[start:end] = [p.doc_id for p in ps]
            tfs[start:end] = [p.tf for p in ps]
        return cls(
            spans, ids, tfs, np.array([d.length for d in ix.docs], dtype=np.int32)
        )

    def write(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for name, arr in (
            ("ids", self.ids),
            ("tfs", self.tfs),
            ("lengths", self.lengths),
        ):
            np.save(folder / name, arr)
        (folder / "terms.json").write_text(json.dumps(self.spans), encoding="utf-8")
        gaps = self.ids.copy()
        for a, b in self.spans.values():
            gaps[a + 1 : b] = np.diff(self.ids[a:b])
        np.savez_compressed(
            folder / "gaps.npz", gaps=gaps, tfs=self.tfs, lengths=self.lengths
        )

    @classmethod
    def read(cls, folder: Path, compressed: bool = False) -> Packed:
        spans: dict[str, tuple[int, int]] = json.loads(
            (folder / "terms.json").read_text(encoding="utf-8")
        )
        if compressed:
            with np.load(folder / "gaps.npz") as data:
                ids = data["gaps"]
                for a, b in spans.values():
                    np.cumsum(ids[a:b], out=ids[a:b])
                return cls(spans, ids, data["tfs"], data["lengths"])
        return cls(
            spans,
            *(
                np.load(folder / (name + ".npy"), mmap_mode="r")
                for name in ("ids", "tfs", "lengths")
            ),
        )


DEFAULT_BM25 = BM25()


def search(
    ix: Index, query: str, scorer: BM25 | TfIdf = DEFAULT_BM25, k: int = 10
) -> list[SearchResult]:
    data = ix.packed
    tree = parse(query)
    before = ix.matching.cache_info().hits
    candidates = np.fromiter(ix.matching(tree), dtype=np.int32)
    logging.getLogger(__name__).debug(
        "cache %s: %s",
        "hit" if ix.matching.cache_info().hits > before else "miss",
        query,
    )
    if not candidates.size or k <= 0:
        return []
    scores = np.zeros(ix.num_docs)
    best = np.zeros_like(scores)
    labels = np.zeros(ix.num_docs, dtype=np.int32)
    words = ["", *dict.fromkeys(positive_words(tree))]
    for j, term in enumerate(words[1:], 1):
        a, b = data.spans.get(term, (0, 0))
        if a == b:
            continue
        ids = data.ids[a:b]
        tf = data.tfs[a:b].astype(np.float64)
        df = b - a
        if isinstance(scorer, BM25):
            norm = scorer.k1 * (
                1 - scorer.b + scorer.b * (data.lengths[ids] / ix.avg_doc_length)
            )
            v = (
                log1p((ix.num_docs - df + 0.5) / (df + 0.5))
                * tf
                * (1 + scorer.k1)
                / (tf + norm)
            )
        else:
            v = (1 + np.log(tf)) * (1 + log((1 + ix.num_docs) / (1 + df)))
        scores[ids] += v
        better = v > best[ids]
        labels[ids[better]] = j
        best[ids[better]] = v[better]
    values = scores[candidates]
    if k < len(values):
        partition = np.argpartition(values, -k)
        candidates = candidates[values >= values[partition[-k]]]
    order = np.lexsort((-candidates, -scores[candidates]))[:k]
    return [
        SearchResult(
            float(scores[i]), int(i), ix.docs[int(i)].title, words[int(labels[i])]
        )
        for i in candidates[order]
    ]
