# ==============================================================================
# Hermes Autonomous Self-Healing Platform — Production Container Image (v1.1.0)
# Multi-stage, rootless, bubblewrap sandboxed, Python 3.12
# ==============================================================================

# ── Stage 1: Builder ──
FROM python:3.12-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels tree-sitter tree-sitter-languages || true

# ── Stage 2: Production Runtime ──
FROM python:3.12-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app

# Install security sandboxing tools: bubblewrap, git, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root hermes user & group (UID 10001)
RUN groupadd -g 10001 hermes && \
    useradd -u 10001 -g hermes -m -s /bin/bash hermes

WORKDIR /app

# Install prebuilt wheels
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copy application source & chown to non-root user
COPY . /app
RUN pip install --no-cache-dir -e ".[all]" || pip install --no-cache-dir -e . && \
    chown -R hermes:hermes /app

USER hermes

EXPOSE 8000

ENTRYPOINT ["hermes"]
CMD ["--help"]
