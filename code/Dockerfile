# ─────────────────────────────────────────────────────────
# ALRS GraphSelect API — Production Docker Image
# Multi-stage build for a minimal, secure runtime image
# ─────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="ALRS GraphSelect API" \
      org.opencontainers.image.description="Automated Literature Review System — GraphSelect Algorithm" \
      org.opencontainers.image.version="2.3.2-beta" \
      org.opencontainers.image.source="https://github.com/HosamKsbaa/MasterProject2" \
      org.opencontainers.image.licenses="MIT"

# Production environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install curl for health-check probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from the builder stage
COPY --from=builder /install /usr/local

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy application code
COPY . .

# Disable browser-open inside the container (headless mode)
ENV OPEN_BROWSER=false

# Drop to non-root
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
