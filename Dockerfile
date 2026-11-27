FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src src
COPY scripts/prepare_data.py scripts/prepare_data.py
RUN uv sync --locked --no-dev --no-editable && python scripts/prepare_data.py && .venv/bin/findex index data --positions --out index07.bin

FROM python:3.12-slim
WORKDIR /app
RUN useradd --system --uid 10001 findex
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/data /app/data
COPY --from=build /app/index07.bin /app/index07.bin
ENV PATH="/app/.venv/bin:$PATH" INDEX_PATH=/app/index07.bin DATA_PATH=/app/data HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8000
CMD ["findex","serve"]
