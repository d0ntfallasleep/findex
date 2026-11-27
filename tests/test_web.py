from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from findex.web.app import app, get_index


@pytest.fixture
def client(index):
    app.state.index = None
    app.state.started = perf_counter()
    app.state.size = 0
    app.state.texts = {doc.path: "red <script>red</script>" for doc in index.docs}
    app.dependency_overrides[get_index] = lambda: index
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_search_pages(client):
    first = client.get("/search", params={"q": "red", "k": 1}).json()
    second = client.get(
        "/search", params={"q": "red", "k": 1, "page": 2, "scorer": "tfidf"}
    ).json()
    assert first["total"] == 2 and len(first["results"]) == 1
    assert first["results"][0]["doc_id"] != second["results"][0]["doc_id"]
    assert client.get("/search?q=red&page=9").json()["results"] == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": " "},
        {"q": "("},
        {"q": "a", "k": 51},
        {"q": "a", "page": 0},
        {"q": "a", "scorer": "bad"},
    ],
)
def test_validation(client, params):
    assert client.get("/search", params=params).status_code == 422


def test_docs_and_stats(client):
    assert client.get("/health").status_code == 200
    assert client.get("/stats").json()["documents"] == 3
    assert client.get("/docs/0").json()["doc_id"] == 0
    assert client.get("/docs/300").status_code == 404
    assert client.get("/doc/0").status_code == 200
    html = client.get("/?q=red").text
    assert "<mark>" in html and "<script>red" not in html


def test_unavailable(client):
    app.dependency_overrides.clear()
    assert client.get("/health").status_code == 503


def test_error_id(client, caplog):
    def fail():
        raise RuntimeError("internal detail")

    app.dependency_overrides[get_index] = fail
    res = client.get("/stats")
    assert res.status_code == 500 and "internal detail" not in res.text
    assert res.headers["x-request-id"] in caplog.text
