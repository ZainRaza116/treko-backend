# Stage 1: Builder
FROM python:3.13-slim-bullseye as builder

# Install build dependencies including cmake
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Set pip configurations
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /app/.venv \
    && . /app/.venv/bin/activate \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --upgrade pip setuptools wheel \
    && pip install git+https://github.com/ageitgey/face_recognition_models

# Stage 2: Runtime
FROM python:3.13-slim-bullseye as runtime

# Create non-root user
RUN useradd -m -u 1000 django

# Install runtime dependencies only
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        wait-for-it \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# Copy virtual environment from builder
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Set working directory and change ownership
WORKDIR /app

# Copy project files including the entrypoint script
COPY --chown=django:django . .

RUN chmod +x /app/docker-entrypoint.sh /app/docker-entrypoint-celery.sh

# Change ownership of the app directory
RUN chown -R django:django /app

# Switch to non-root user
USER django

# Expose port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]