import logging
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from findex.corpus import iter_documents
from findex.models import Index
from findex.query import parse, positive_words
from findex.ranking import BM25, TfIdf, snippet
from findex.store import load
from findex.vector import Packed, search

log = logging.getLogger(__name__)
base = Path(__file__).parent
templates = Jinja2Templates(directory=base / "templates")


@dataclass
class Settings:
    index_path: Path
    data: Path


def get_settings() -> Settings:
    return Settings(
        Path(os.getenv("INDEX_PATH", "index07.bin")),
        Path(os.getenv("DATA_PATH", "data")),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = get_settings()
    app.state.started = perf_counter()
    app.state.index = None
    app.state.texts = {}
    app.state.size = 0
    try:
        ix = load(cfg.index_path)
        if folder := os.getenv("PACKED_PATH"):
            ix.packed = Packed.read(Path(folder))
        app.state.texts = {doc.doc_id: doc.text for doc in iter_documents(cfg.data)}
        app.state.size = cfg.index_path.stat().st_size
        app.state.index = ix
    except OSError:
        log.exception("Не вдалося відкрити індекс %s", cfg.index_path)
    yield
    app.state.index = None
    app.state.texts.clear()


def get_index(request: Request) -> Index:
    ix = request.app.state.index
    if ix is None:
        raise HTTPException(503, "Індекс ще не завантажено")
    return ix


type Ix = Annotated[Index, Depends(get_index)]


class Params(BaseModel):
    q: str = Field(min_length=1, max_length=500, pattern=r"\S")
    k: int = Field(default=5, ge=1, le=50)
    scorer: Literal["bm25", "tfidf"] = "bm25"
    page: int = Field(default=1, ge=1)


class Hit(BaseModel):
    doc_id: int
    title: str
    score: float
    snippet: str


class Results(BaseModel):
    query: str
    total: int
    took_ms: float
    results: list[Hit]


class DocumentOut(BaseModel):
    doc_id: int
    title: str
    text: str


def run_search(request: Request, params: Params, ix: Index) -> Results:
    start = perf_counter()
    try:
        terms = set(positive_words(parse(params.q)))
        ranked = search(
            ix, params.q, BM25() if params.scorer == "bm25" else TfIdf(), ix.num_docs
        )
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "Некоректний запит: " + str(exc)) from exc
    offset = (params.page - 1) * params.k
    hits: list[Hit] = []
    for item in ranked[offset : offset + params.k]:
        text = request.app.state.texts.get(ix.docs[item.doc_id].path, "")
        hits.append(
            Hit(
                doc_id=item.doc_id,
                title=item.title,
                score=item.score,
                snippet=snippet(text, item.best_term, terms),
            )
        )
    return Results(
        query=params.q,
        total=len(ranked),
        took_ms=(perf_counter() - start) * 1000,
        results=hits,
    )


def search_route(
    request: Request, params: Annotated[Params, Query()], ix: Ix
) -> Results:
    return run_search(request, params, ix)


def document(doc_id: int, request: Request, ix: Ix) -> DocumentOut:
    if not 0 <= doc_id < ix.num_docs:
        raise HTTPException(404, "Невідомий документ")
    doc = ix.docs[doc_id]
    return DocumentOut(
        doc_id=doc_id, title=doc.title, text=request.app.state.texts.get(doc.path, "")
    )


app = FastAPI(title="findex", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=base / "static"), name="static")
app.get("/search")(search_route)
app.get("/docs/{doc_id}")(document)


@app.middleware("http")
async def request_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    ident = uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request_id=%s path=%s", ident, request.url.path)
        response = JSONResponse(
            {"detail": "Внутрішня помилка", "request_id": ident}, status_code=500
        )
    response.headers["X-Request-ID"] = ident
    return response


@app.get("/health")
def health(ix: Ix) -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def stats(request: Request, ix: Ix) -> dict[str, float]:
    return {
        "documents": ix.num_docs,
        "vocabulary": len(ix),
        "index_bytes": request.app.state.size,
        "uptime_seconds": perf_counter() - request.app.state.started,
    }


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request, ix: Ix, q: str = "", page: Annotated[int, Query(ge=1)] = 1
) -> Response:
    result = None
    error = ""
    if q:
        try:
            result = run_search(request, Params(q=q, page=page), ix)
        except (HTTPException, ValueError) as exc:
            error = (
                exc.detail
                if isinstance(exc, HTTPException)
                else "Перевір довжину та зміст запиту."
            )
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"q": q, "page": page, "result": result, "error": error},
    )


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def doc_page(doc_id: int, request: Request, ix: Ix) -> Response:
    return templates.TemplateResponse(
        request=request, name="doc.html", context={"doc": document(doc_id, request, ix)}
    )
