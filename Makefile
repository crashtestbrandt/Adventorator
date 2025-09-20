.PHONY: dev test lint type run docker

uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

dev:
	uv venv || true
	. .venv/bin/activate && uv pip install -r requirements.txt
	. .venv/bin/activate && uv pip install -e .

run:
	. .venv/bin/activate && UVICORN_LOG_LEVEL=info uvicorn --app-dir src Adventorator.app:app --reload --host 0.0.0.0 --port 18000

# Kill any process already bound to 18000 (macOS/Linux). Ignores errors if none.
kill-port:
	@PID=$$(lsof -ti tcp:18000 || true); \
	if [ -n "$$PID" ]; then echo "Killing process on :18000 (PID $$PID)"; kill $$PID || true; sleep 1; fi

# Kill process bound to default Postgres port (5432) if it's an old dev container or local instance
kill-db-port:
	@PID=$$(lsof -ti tcp:5432 || true); \
	if [ -n "$$PID" ]; then echo "Killing process on :5432 (PID $$PID)"; kill $$PID || true; sleep 1; else echo "No process on :5432"; fi

# Convenience target: free port then run server
run-dev: kill-port run

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

coverage:
	. .venv/bin/activate && pytest --cov=Adventorator --cov-report=term-missing --cov-fail-under=80

mutation-guard:
	. .venv/bin/activate && python scripts/check_mutation_guard.py

security:
	. .venv/bin/activate && bandit -q -r src -ll

quality-artifacts:
	. .venv/bin/activate && python scripts/validate_prompts_and_contracts.py

ai-evals:
	. .venv/bin/activate && python scripts/run_ai_evals.py

quality-gates: coverage mutation-guard security quality-artifacts ai-evals

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

alembic-up-one:
	. .venv/bin/activate && PYTHONPATH=./src alembic upgrade +1

alembic-up-all:
	. .venv/bin/activate && PYTHONPATH=./src alembic upgrade heads

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
	docker compose up -d --build db app

# Use the docker-specific env file (copy from .env.docker.example -> .env.docker)
compose-dev:
	@if [ ! -f .env.docker ]; then echo "Missing .env.docker (copy from .env.docker.example)"; exit 1; fi
	docker compose --env-file .env.docker up -d --build db app

# Auto-detect a free DB port (tries 5432, 55432, 56432) then launches compose with that DB_PORT
compose-dev-auto:
	@if [ ! -f .env.docker ]; then echo "Missing .env.docker (copy from .env.docker.example)"; exit 1; fi; \
	CANDIDATES="5432 55432 56432"; SEL=""; \
	for p in $$CANDIDATES; do if ! lsof -ti tcp:$$p >/dev/null 2>&1; then SEL=$$p; break; fi; done; \
	if [ -z "$$SEL" ]; then echo "No free candidate DB port found (tried: $$CANDIDATES)"; exit 1; fi; \
	echo "Selected free DB_PORT=$$SEL"; \
	DB_PORT=$$SEL docker compose --env-file .env.docker up -d --build db app

# Start only the app (assumes you are pointing DATABASE_URL at an external/local Postgres)
compose-dev-app-only:
	@if [ ! -f .env.docker ]; then echo "Missing .env.docker (copy from .env.docker.example)"; exit 1; fi
	docker compose --env-file .env.docker up -d --build app

compose-down:
	docker compose down

# Remove containers plus orphans (no volumes)
compose-down-orphans:
	docker compose down --remove-orphans

# Remove containers, orphans, and named/anonymous volumes (DB reset)
compose-clean:
	docker compose down --remove-orphans --volumes

# Full prune of dangling images/volumes/networks (safe if other projects not relying)
compose-prune:
	docker system prune -f --volumes

# Convenience: stop and remove only orphan containers from previous compose services
compose-orphans-rm:
	@orphans=$$(docker ps -a --filter "name=adventorator" --format '{{.Names}}' | grep orphan || true); \
	if [ -n "$$orphans" ]; then echo "Removing orphans: $$orphans"; docker rm -f $$orphans || true; else echo "No orphan containers found"; fi

