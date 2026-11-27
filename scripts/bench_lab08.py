from functools import partial
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from timeit import repeat

from findex.corpus import Document, iter_documents
from findex.index import build_documents
from findex.ranking import search as scalar
from findex.vector import Packed, search


def main():
    for factor in (1, 10):
        docs = (
            Document(f"{i}/{d.doc_id}", d.path, d.text)
            for i in range(factor)
            for d in iter_documents(Path("data/war-of-the-worlds"))
        )
        ix = build_documents(docs, True)
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            ix.packed.write(folder)
            ix.packed = Packed.read(folder)
            size = sum(p.stat().st_size for p in folder.glob("*.npy"))
            gaps = (folder / "gaps.npz").stat().st_size
            print(
                f"Масиви ×{factor}: {size} байт, gap + DEFLATE: {gaps} байт (словник термів окремо)."
            )
            for q in ("the", "bacteria", "mars OR earth OR cylinder"):
                assert [r.doc_id for r in scalar(ix, q)] == [
                    r.doc_id for r in search(ix, q)
                ]
                times = [
                    median(repeat(partial(fn, ix, q), number=100, repeat=7)) * 10
                    for fn in (scalar, search)
                ]
                print(
                    f"| {factor} | {q} | {times[0]:.4f} | {times[1]:.4f} | {times[0] / times[1]:.2f} |"
                )


if __name__ == "__main__":
    main()
