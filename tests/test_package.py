import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from findex.cli import app
from findex.corpus import Document
from findex.index import build_documents
from findex.models import Posting
from findex.ranking import BM25, TfIdf
from findex.search import merge
from findex.store import load, save

texts = st.lists(
    st.lists(st.sampled_from(["mars", "земля", "café"]), max_size=10).map(" ".join),
    max_size=7,
)


def build(texts):
    return build_documents(
        (Document(str(i), Path(str(i)), text) for i, text in enumerate(texts)), True
    )


@pytest.mark.slow
@given(texts, st.sampled_from(["json", "bin"]))
@settings(max_examples=50)
def test_save_property(texts, ext):
    ix = build(texts)
    with TemporaryDirectory() as folder:
        path = Path(folder) / ("index." + ext)
        save(ix, path)
        assert load(path) == ix


@given(texts)
def test_sorted_postings(texts):
    ix = build(texts)
    for term in ix:
        ids = [p.doc_id for p in ix[term]]
        assert ids == sorted(set(ids))


@given(
    st.sets(st.integers()),
    st.sets(st.integers()),
    st.sampled_from(["AND", "OR", "NOT"]),
)
def test_merge_property(a, b, op):
    expected = {"AND": a & b, "OR": a | b, "NOT": a - b}
    assert merge(sorted(a), sorted(b), op) == sorted(expected[op])


@pytest.mark.parametrize("model", [BM25(), TfIdf()])
def test_rarity_and_diminishing_returns(model):
    ix = build(["mars rare", "mars mars", "mars mars"])

    def score(term, tf):
        return model.score(term, Posting(0, tf), ix)

    assert score("rare", 1) > score("mars", 1)
    assert (
        0 < score("mars", 20) - score("mars", 19) < score("mars", 2) - score("mars", 1)
    )


def test_length_normalization():
    ix = build(["mars", "mars " + "red " * 50])
    short, long = ix["mars"]
    assert BM25().score("mars", short, ix) > BM25().score("mars", long, ix)
    assert TfIdf().score("mars", short, ix) == TfIdf().score("mars", long, ix)


def test_cli(tmp_path):
    corpus = tmp_path / "texts"
    corpus.mkdir()
    (corpus / "one.txt").write_text("Red Mars", encoding="utf-8")
    dest = tmp_path / "ix.bin"
    runner = CliRunner()
    assert (
        runner.invoke(
            app,
            ["index", str(corpus), "--out", str(dest), "--positions", "--limit", "1"],
        ).exit_code
        == 0
    )
    for mode in ("bm25", "tfidf"):
        result = runner.invoke(
            app,
            [
                "-vv",
                "search",
                str(dest),
                "mars",
                "--scorer",
                mode,
                "--json",
                "--data",
                str(corpus),
            ],
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["snippet"] == "Red **Mars**"
        assert "DEBUG" in result.stderr
    assert "Red Mars" in runner.invoke(app, ["search", str(dest), "mars"]).stdout
    assert "Токенів: 2" in runner.invoke(app, ["stats", str(dest)]).stdout
    for args in (["search", str(dest), "("], ["stats", str(tmp_path / "missing")]):
        result = runner.invoke(app, args)
        assert result.exit_code and len(result.stderr.splitlines()) == 1
