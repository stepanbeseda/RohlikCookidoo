FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so that code changes do not reinstall them
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY rohlik_cookidoo ./rohlik_cookidoo
COPY server.py ./
RUN uv sync --frozen --no-dev

# Run as an unprivileged user; /data holds the pantry and memory files
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data \
    && chown app /data
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATA_DIR=/data
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "server.py"]
