FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	UV_SYSTEM_PYTHON=1

WORKDIR /app

# System deps for psycopg, build tools, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
	curl build-essential libpq-dev && \
	rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
	~/.local/bin/uv --version

# Copy metadata and lockfiles first for better layer caching
COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY scripts ./scripts

# Install Python deps (wheel cache inside image). requirements.txt includes "-e ."
RUN ~/.local/bin/uv pip install -r requirements.txt
COPY config.toml ./config.toml

EXPOSE 18000

# Default command: run the FastAPI app
CMD ["python", "-m", "uvicorn", "Adventorator.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "18000"]

