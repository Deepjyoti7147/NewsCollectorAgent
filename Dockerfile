# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Only copy requirements first to leverage layer cache
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Create non-root user and install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /sbin/nologin -d /app newscollector

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=newscollector:newscollector collector/ ./collector/
COPY --chown=newscollector:newscollector main.py .

USER newscollector

# Healthcheck: verify the API is responsive
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${API_PORT:-5000}/health || exit 1

# Memory-conscious defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONMALLOC=malloc \
    LOG_LEVEL=INFO \
    API_PORT=5000

ENTRYPOINT ["python", "-u", "main.py"]
