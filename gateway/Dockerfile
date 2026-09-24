ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* README.md LICENSE ./
COPY packages ./packages
COPY registry ./registry
COPY gateway ./gateway
COPY servers ./servers

RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MCP_TRANSPORT=streamable-http \
    MCP_LOG_FORMAT=json

RUN groupadd -r mcp && useradd -r -g mcp -u 10001 mcp
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

USER mcp
EXPOSE 8000

ENTRYPOINT ["python", "-m", "gateway.main"]
