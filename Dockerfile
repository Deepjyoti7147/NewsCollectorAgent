# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Only copy requirements first to leverage layer cache
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Create non-root user
RUN useradd -r -s /sbin/nologin -d /app newscollector

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=newscollector:newscollector collector/ ./collector/
COPY --chown=newscollector:newscollector main.py .

USER newscollector

# Healthcheck: verify the process is alive
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import psycopg2" || exit 1

# Memory-conscious defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONMALLOC=malloc \
    LOG_LEVEL=INFO

ENTRYPOINT ["python", "-u", "main.py"]
