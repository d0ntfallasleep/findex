"""Лише для порівняння: той самий пошук запускається в потоці event loop."""

from typing import Annotated

from fastapi import FastAPI, Query, Request

from findex.web.app import (
    Ix,
    Params,
    Results,
    health,
    lifespan,
    request_log,
    run_search,
)

app = FastAPI(lifespan=lifespan)
app.middleware("http")(request_log)
app.get("/health")(health)


@app.get("/search")
async def baseline(
    request: Request, params: Annotated[Params, Query()], ix: Ix
) -> Results:
    return run_search(request, params, ix)
