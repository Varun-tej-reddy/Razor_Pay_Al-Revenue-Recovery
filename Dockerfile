# Multi-stage production-grade Dockerfile for AI Revenue Recovery Agent
# Stage 1: Build & Dependencies
FROM python:3.9-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal Runtime Image
FROM python:3.9-slim AS runtime

WORKDIR /app

# Copy installed wheels & binaries from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY agent/ ./agent/
COPY data/ ./data/
COPY storage/ ./storage/
COPY api/ ./api/
COPY dashboard/ ./dashboard/
COPY .env.example ./.env.example

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////app/data/recovery_audit.db

# Create data directory for SQLite persistence volume
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
