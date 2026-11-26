"""Друкує таблицю P@5 та контрольні приклади у Markdown."""

from pathlib import Path

from findex.models import Posting
from findex.ranking import BM25, TfIdf, search
from findex.store import open_index

# Розділи позначено за подіями сюжету. Формат: частина.розділ.
LABELS = {
    '"falling star" OR ogilvy': ["1.1", "1.2", "1.3"],
    "cylinder opens": ["1.4"],
    '"heat ray"': ["1.5", "1.6", "1.12"],
    "storm OR lightning": ["1.10"],
    "weybridge OR shepperton": ["1.12"],
    "curate": ["1.13", "2.1", "2.3", "2.4"],
    "refugees OR exodus": ["1.14", "1.16", "1.17"],
    '"thunder child"': ["1.17"],
    "artilleryman": ["1.11", "1.12", "2.7"],
    "bacteria": ["2.6", "2.8", "2.10"],
}


def chapter(index, doc_id):
    name = Path(index.docs[doc_id].path).stem.split("-")
    return f"{name[1]}.{int(name[3])}"


def main():
    with open_index(Path("index03.bin")) as ix:
        print("| Запит | Розділи за розміткою | TF-IDF | BM25 |")
        print("|---|---|---:|---:|")
        for query, relevant in LABELS.items():
            values = []
            for scorer in (TfIdf(), BM25()):
                hits = search(ix, query, scorer, k=5)
                correct = sum(chapter(ix, r.doc_id) in relevant for r in hits)
                values.append(correct / 5)
            print(
                f"| {query} | {', '.join(relevant)} | {values[0]:.2f} | {values[1]:.2f} |"
            )

        model = BM25()
        print("\n**Три перевірки BM25**\n")
        hits = search(ix, "bacteria OR martians", model, k=ix.num_docs)
        rare = next(r for r in hits if r.doc_id in {p.doc_id for p in ix["bacteria"]})
        common = next(
            r for r in hits if r.doc_id not in {p.doc_id for p in ix["bacteria"]}
        )
        assert rare.score > common.score
        print(
            f"1. У запиті `bacteria OR martians` df слів — {ix.df('bacteria')} і {ix.df('martians')}. "
            f"Розділ {chapter(ix, rare.doc_id)} зі словом bacteria отримав {rare.score:.3f}, "
            f"найкращий лише з martians ({chapter(ix, common.doc_id)}) — {common.score:.3f}."
        )
        doc_id = ix["bacteria"][0].doc_id
        scores = [
            model.score("bacteria", Posting(doc_id, n), ix) for n in (1, 2, 19, 20)
        ]
        assert scores[3] - scores[2] < scores[1] - scores[0]
        print(
            f"2. Для довжини розділу {chapter(ix, doc_id)} та корпусного df слова bacteria "
            f"змінюю тільки tf. Приріст 1→2: {scores[1] - scores[0]:.4f}; "
            f"19→20: {scores[3] - scores[2]:.4f}. Це контрольований розрахунок."
        )
        once = sorted(
            (p for p in ix["tripod"] if p.tf == 1),
            key=lambda p: ix.doc_length(p.doc_id),
        )
        a, b = once[0], once[-1]
        assert model.score("tripod", a, ix) > model.score("tripod", b, ix)
        print(
            f"3. У розділах {chapter(ix, a.doc_id)} і {chapter(ix, b.doc_id)} слово tripod є один раз. "
            f"Довжини — {ix.doc_length(a.doc_id)} та {ix.doc_length(b.doc_id)} токенів, "
            f"бали — {model.score('tripod', a, ix):.3f} та {model.score('tripod', b, ix):.3f}."
        )


if __name__ == "__main__":
    main()
