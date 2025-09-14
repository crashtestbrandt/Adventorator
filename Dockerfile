FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	UV_SYSTEM_PYTHON=1

WORKDIR /app

# Install curl for healthchecks; avoid heavy build deps in runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
	~/.local/bin/uv --version

# Copy metadata and lockfiles first for better layer caching
COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY scripts ./scripts

# Install Python deps (requirements.txt includes "-e .")
RUN ~/.local/bin/uv pip install -r requirements.txt
COPY config.toml ./config.toml

# Create non-root user and set ownership
RUN useradd -m -u 10001 appuser \
	&& mkdir -p /app/logs \
	&& chown -R appuser:appuser /app
USER appuser

EXPOSE 18000

# Basic container-level healthcheck matching compose
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:18000/healthz >/dev/null || exit 1

# Default command: run the FastAPI app
CMD ["python", "-m", "uvicorn", "Adventorator.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "18000"]

