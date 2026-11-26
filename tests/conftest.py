import pytest

from findex.index import build_index


@pytest.fixture
def index(tmp_path):
    for name, text in [("a", "red red mars"), ("b", "red earth"), ("c", "")]:
        (tmp_path / f"{name}.txt").write_text(text, encoding="utf-8")
    return build_index(tmp_path, positions=True)
