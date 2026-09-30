FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY zombie_saas_coordinator/ ./zombie_saas_coordinator/

# Expose Cloud Run port
ENV PORT=8080
EXPOSE 8080

# Run the FastAPI server
CMD ["uvicorn", "zombie_saas_coordinator.main:app", "--host", "0.0.0.0", "--port", "8080"]
