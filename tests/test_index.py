from pathlib import Path

import pytest

from findex.search import search
from findex.store import load, save


@pytest.mark.parametrize("engine", ["merge", "set"])
@pytest.mark.parametrize(
    ("query", "names"),
    [
        ("red mars", ["a"]),
        ("mars OR earth", ["a", "b"]),
        ("red NOT earth", ["a"]),
        ("NOT red", ["c"]),
        ("mars OR earth AND missing", ["a"]),
        ("unknown", []),
    ],
)
def test_search(index, engine, query, names):
    ids = search(index, query, engine)
    assert ids == sorted(set(ids))
    assert sorted(Path(index.docs[i].path).stem for i in ids) == names


@pytest.mark.parametrize("suffix", [".json", ".bin"])
def test_roundtrip(index, tmp_path, suffix):
    path = tmp_path / ("index" + suffix)
    save(index, path)
    assert load(path) == index
    posting = next(p for p in index.postings["red"] if p.tf == 2)
    assert index.positions["red"][posting.doc_id] == [0, 1]
    assert index.docs[posting.doc_id].length == 3
