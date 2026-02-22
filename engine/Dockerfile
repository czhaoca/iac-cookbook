FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source
COPY . .

# Non-root user
RUN groupadd -r nimbus && useradd -r -g nimbus -d /app nimbus \
    && mkdir -p /app/data /app/config \
    && chown -R nimbus:nimbus /app
USER nimbus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "nimbus.app:app", "--host", "0.0.0.0", "--port", "8000"]
