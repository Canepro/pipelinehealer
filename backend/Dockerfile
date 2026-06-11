# PipelineHealer Backend Dockerfile
FROM python:3.12-slim

# git is required for local Codex handoff execution (workspace clones).
# The codex CLI is not bundled; install it in a derived image or use a
# loopback Codex App Server when enabling AGENT_HANDOFF_LOCAL_CODEX_ENABLED.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy package metadata + source before install so hatchling can resolve readme/package files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies using uv
RUN uv pip install --system .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
