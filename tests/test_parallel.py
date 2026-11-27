import subprocess
import sys

import pytest

from findex.corpus import iter_documents
from findex.index import build_documents, build_index
from findex.store import save


@pytest.mark.parametrize("positions", [False, True])
@pytest.mark.parametrize("executor", ["serial", "threads", "processes"])
def test_same_as_lab4(tmp_path, executor, positions):
    for i in range(6):
        (tmp_path / f"{i}.txt").write_text(f"Mars mars день {i}", encoding="utf-8")
    (tmp_path / "broken.txt").write_bytes(b"\xff")
    reference = build_documents(iter_documents(tmp_path), positions)
    result = build_index(tmp_path, positions, workers=4, executor=executor)
    assert result == reference
    for suffix in (".json", ".bin"):
        old, new = (tmp_path / (s + suffix) for s in ("old", "new"))
        save(reference, old)
        save(result, new)
        assert old.read_bytes() == new.read_bytes()


def test_worker_error(tmp_path):
    # NUL у назві відтворює виняток усередині дочірнього процесу.
    script = tmp_path / "failure.py"
    script.write_text(
        """from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from findex.index import Chunk, build_partial

if __name__ == "__main__":
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        pool.submit(build_partial, Chunk(Path("."), [Path(chr(0))], 0, False)).result()
""",
        encoding="utf-8",
    )
    run = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        run.returncode and "build_partial" in run.stderr and "ValueError" in run.stderr
    )
