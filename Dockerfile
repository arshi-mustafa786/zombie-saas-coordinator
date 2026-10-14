FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging for Cloud Logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PORT=8080

WORKDIR /app

# Step 1: Install runtime dependencies with extended network timeout (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt

# Step 2: Install project itself (requires pyproject.toml and README.md)
COPY pyproject.toml README.md ./
COPY zombie_saas_coordinator/ ./zombie_saas_coordinator/
RUN pip install --no-cache-dir --no-deps .

# Create a non-root application user for Cloud Run security compliance
RUN useradd -u 1001 -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Production Uvicorn entry point with Cloud Run PORT binding and keep-alive optimization
CMD ["uvicorn", "zombie_saas_coordinator.main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "75"]
