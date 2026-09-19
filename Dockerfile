# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    HF_HOME=/home/appuser/.cache/huggingface

# Create a non-root user and group
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements-api.txt

# Copy application source and data assets needed for embedding
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser api/ ./api/
COPY --chown=appuser:appuser data/raw/ ./data/raw/
COPY --chown=appuser:appuser data/processed/chunks.json ./data/processed/chunks.json

# Create chroma_db and HuggingFace cache directories with proper ownership
RUN mkdir -p /app/data/chroma_db /home/appuser/.cache && \
    chown -R appuser:appuser /app /home/appuser

# Switch to non-root user before building vector collections
USER appuser

# Build and bake the vector databases directly into the final image layer
RUN python src/embed_and_store.py && \
    python src/index_case_law.py

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
