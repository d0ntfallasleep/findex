from pathlib import Path

import numpy as np
import pytest

from findex.corpus import Document
from findex.index import build_documents
from findex.ranking import BM25, TfIdf
from findex.ranking import search as scalar
from findex.vector import Packed, search


@pytest.mark.parametrize("model", [BM25(), TfIdf()])
@pytest.mark.parametrize(
    "q",
    [
        "red",
        "mars OR earth",
        "NOT mars",
        '"red mars"',
        "unknown",
        "red OR earth OR mars",
    ],
)
@pytest.mark.parametrize("k", [0, 1, 2, 10])
def test_rank(index, model, q, k):
    old = scalar(index, q, model, k)
    new = search(index, q, model, k)
    assert [r.doc_id for r in new] == [r.doc_id for r in old]
    assert [r.score for r in new] == pytest.approx([r.score for r in old])
    assert [r.best_term for r in new] == [r.best_term for r in old]


def test_ties():
    ix = build_documents(
        (Document(str(i), Path(str(i)), "mars") for i in range(15)), False
    )
    assert [r.doc_id for r in search(ix, "mars", k=3)] == [14, 13, 12]


@pytest.mark.parametrize("compressed", [True, False])
def test_packed(index, tmp_path, compressed):
    index.packed.write(tmp_path)
    copy = Packed.read(tmp_path, compressed)
    for field in ("ids", "tfs", "lengths"):
        assert np.array_equal(getattr(index.packed, field), getattr(copy, field))
    assert copy.ids.dtype == np.int32 and isinstance(copy.ids, np.memmap) == (
        not compressed
    )
