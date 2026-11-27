import asyncio
import json
import logging
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from rich.text import Text

from findex.index import Executor, build_index
from findex.query import parse, positive_words
from findex.ranking import BM25, TfIdf, snippet
from findex.ranking import search as ranked_search
from findex.store import open_index, save

app = typer.Typer(help="Пошук у текстовому корпусі.")


@app.callback()
def configure(verbose: Annotated[int, typer.Option("-v", count=True)] = 0) -> None:
    level = [logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)]
    logging.basicConfig(level=level, format="%(levelname)s %(message)s", force=True)


@contextmanager
def errors() -> Generator[None, None, None]:
    try:
        yield
    except (OSError, ValueError) as exc:
        typer.echo(f"Помилка: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def index(
    corpus: Path,
    out: Annotated[Path, typer.Option("--out")],
    positions: bool = False,
    workers: Annotated[int, typer.Option(min=1)] = 1,
    executor: Executor = "serial",
    limit: Annotated[int | None, typer.Option(min=0)] = None,
) -> None:
    with errors():
        if not (corpus.is_dir() or (corpus.is_file() and corpus.suffix == ".jsonl")):
            raise ValueError(f"Папку корпусу не знайдено: {corpus}")
        with Progress(console=Console(stderr=True)) as progress:
            task = progress.add_task("Індексація", total=None)
            ix = build_index(corpus, positions, limit, workers, executor)
            progress.update(task, total=1, completed=1)
        save(ix, out)
        typer.echo(f"{ix.num_docs} документів, {len(ix)} термів")


@app.command()
def search(
    index: Path,
    query: str,
    k: Annotated[int, typer.Option(min=1)] = 10,
    scorer: Literal["bm25", "tfidf"] = "bm25",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    data: Path = Path("data"),
) -> None:
    with errors(), open_index(index) as ix:
        results = ranked_search(ix, query, BM25() if scorer == "bm25" else TfIdf(), k)
        terms = set(positive_words(parse(query)))
        table = Table("Бал", "Розділ", "Фрагмент")
        for hit in results:
            doc = ix.docs[hit.doc_id]
            path = data / doc.path
            fragment = (
                snippet(path.read_text(encoding="utf-8"), hit.best_term, terms)
                if path.is_file()
                else ""
            )
            if json_output:
                typer.echo(
                    json.dumps(
                        {
                            "doc_id": hit.doc_id,
                            "title": hit.title,
                            "path": doc.path,
                            "score": hit.score,
                            "snippet": fragment,
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                styled = Text()
                for i, piece in enumerate(fragment.split("**")):
                    styled.append(piece, style="bold yellow" if i % 2 else "")
                table.add_row(f"{hit.score:.3f}", Text(hit.title), styled)
        if not json_output:
            Console().print(table)


@app.command()
def stats(index: Path) -> None:
    with errors(), open_index(index) as ix:
        typer.echo(
            f"Документів: {ix.num_docs}\nТокенів: {sum(d.length for d in ix.docs)}\nРізних токенів: {len(ix)}"
        )
        terms = Counter({t: sum(p.tf for p in ix[t]) for t in ix})
        table = Table("Топ-50 термів", "Частота")
        for term, count in terms.most_common(50):
            table.add_row(term, str(count))
        Console().print(table)


@app.command("crawl")
def crawl_command(
    seed_url: str,
    max_pages: Annotated[int, typer.Option(min=1)] = 500,
    concurrency: Annotated[int, typer.Option(min=1)] = 10,
    per_host: Annotated[int, typer.Option(min=1)] = 2,
    delay: Annotated[float, typer.Option(min=0)] = 0.05,
    out: Path = Path("data/crawl.jsonl"),
) -> None:
    from findex.crawler.command import collect

    with errors():
        asyncio.run(collect(seed_url, max_pages, concurrency, per_host, delay, out))
