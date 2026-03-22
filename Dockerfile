# ---- builder stage ----
FROM cgr.dev/chainguard/python:latest-dev AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself
COPY ollama_top/ ollama_top/
RUN uv sync --frozen --no-dev

# ---- runtime stage ----
FROM cgr.dev/chainguard/python:latest-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy the full virtual environment and project from builder
COPY --from=builder /app /app

# Create writable directory for SQLite DB
RUN mkdir -p /data && chown nonroot:nonroot /data
VOLUME ["/data"]

ENV OLLAMA_HOST=http://host.docker.internal:11434
ENV DB_PATH=/data/history.db

USER nonroot

ENTRYPOINT ["uv", "run", "ollama-top"]
