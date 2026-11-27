from findex.index import build_index
from findex.vector import search


def test_bench_search(benchmark, index):
    assert benchmark(search, index, "red OR mars")
    assert benchmark.stats.stats.median < 0.003


def test_bench_build(benchmark, index, tmp_path):
    assert benchmark(build_index, tmp_path, True) == index
    assert benchmark.stats.stats.median < 0.01
