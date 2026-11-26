import pytest

from findex.index import build_index
from findex.query import And, Not, Or, Phrase, Term, parse
from findex.ranking import search, snippet
from findex.store import open_index, save


def test_trees():
    a, b, c = map(Term, "abc")
    assert parse("a OR b c") == Or(a, And(b, c))
    assert parse('a AND (b OR c) NOT d "event loop"') == (
        a & (b | c) & Not(Term("d")) & Phrase(("event", "loop"))
    )


@pytest.mark.parametrize("query", ["a OR", "(a", "a)", '""', '"broken'])
def test_invalid(query):
    with pytest.raises(ValueError):
        parse(query)


def test_index_and_phrase(tmp_path):
    for name, text in [("a", "red red moon"), ("b", "red bright moon")]:
        (tmp_path / (name + ".txt")).write_text(text, encoding="utf-8")
    ix = build_index(tmp_path, True)
    assert len(ix) == 3 and ix.num_docs == 2 and ix.df("red") == 2
    assert ix.avg_doc_length == 3 and set(ix) == {"red", "moon", "bright"}
    assert "moon" in ix and len(ix["moon"]) == 2
    with pytest.raises(KeyError):
        _ = ix["absent"]
    file = tmp_path / "index.bin"
    save(ix, file)
    with pytest.raises(RuntimeError), open_index(file) as loaded:
        assert len(search(loaded, '"red moon"')) == 1
        search(loaded, '"red moon"')
        assert loaded.matching.cache_info().hits == 1
        raise RuntimeError
    assert loaded.matching.cache_info().currsize == 0
    assert snippet("A red moon", "moon", {"moon"}) == "A red **moon**"
