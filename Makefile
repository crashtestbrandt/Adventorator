.PHONY: dev test lint type run docker

uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

dev:
	uv venv || true
	. .venv/bin/activate && uv pip install -r requirements.txt
	. .venv/bin/activate && uv pip install -e .

run:
	. .venv/bin/activate && UVICORN_LOG_LEVEL=info uvicorn --app-dir src Adventorator.app:app --reload --host 0.0.0.0 --port 18000

tunnel:
	cloudflared tunnel --url http://127.0.0.1:18000

# Named Cloudflare Tunnel helpers (requires Cloudflare account & zone)
# One-time: `cloudflared login`, then create and route DNS to your hostname.
# Example hostname: adv-dev.yourdomain.com
tunnel-dev-run:
	cloudflared tunnel run adventorator-dev

tunnel-dev-create:
	cloudflared tunnel create adventorator-dev

# Set a DNS record for your tunnel to a stable hostname
# Usage: make tunnel-dev-dns HOST=adv-dev.example.com
tunnel-dev-dns:
	@if [ -z "$(HOST)" ]; then echo "HOST is required (e.g., make tunnel-dev-dns HOST=adv-dev.example.com)"; exit 1; fi
	cloudflared tunnel route dns adventorator-dev $(HOST)

test:
	. .venv/bin/activate && pytest

lint:
	. .venv/bin/activate && ruff check src tests

lint-fix:
	. .venv/bin/activate && ruff check --fix src tests

type:
	. .venv/bin/activate && mypy src

format:
	. .venv/bin/activate && ruff format src tests

# --- Pending expiration helper ---
expire-pending:
	. .venv/bin/activate && python -m Adventorator.scripts.expire_pending

clean:
	rm -rf .venv

db-up:
	docker run --rm -d --name advdb -e POSTGRES_PASSWORD=adventorator \
		-e POSTGRES_USER=adventorator -e POSTGRES_DB=adventorator \
		-p 5432:5432 postgres:16

alembic-init:
	alembic init -t async migrations

alembic-rev:
	. .venv/bin/activate && PYTHONPATH=./src alembic revision --autogenerate -m "$(m)"

alembic-up:
	. .venv/bin/activate && PYTHONPATH=./src alembic upgrade head

# Alias to match README instructions
db-upgrade: alembic-up

alembic-down:
	. .venv/bin/activate && PYTHONPATH=./src alembic downgrade -1

# Build docs/implementation_plan.md from GitHub issues titled "Phase N"
.PHONY: implementation-plan
implementation-plan:
	. .venv/bin/activate && python3 scripts/build_implementation_plan.py

.PHONY: compose-up compose-down
compose-up:
	docker compose up -d --build db app cli-sink

compose-down:
	docker compose down

