.PHONY: dev test lint type run docker test-idempotency

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

# Idempotency and rollback test suite (TASK-CDA-IMPORT-RERUN-19C)
test-idempotency:
	. .venv/bin/activate && pytest tests/importer/test_importer_idempotency.py tests/importer/test_importer_rollback.py -v

.PHONY: smoke
smoke:
	pytest -m smoke -q

.PHONY: seed-encounter
seed-encounter:
	PYTHONPATH=./src python scripts/seed_encounter.py

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
	. .venv/bin/activate && python scripts/validate_contracts.py

ai-evals:
	. .venv/bin/activate && python scripts/run_ai_evals.py

quality-gates: coverage mutation-guard security quality-artifacts ai-evals

# --- Pending expiration helper ---
expire-pending:
	. .venv/bin/activate && python -m Adventorator.scripts.expire_pending

# -------------- CLEANING & RESET --------------
.PHONY: clean clean-local clean-build clean-pyc clean-venv clean-logs clean-sqlite clean-caches \
	clean-docker clean-compose clean-docker-related clean-docker-prune clean-warning \
	clean-docker-all-images clean-docker-unused-images clean-docker-images-project \
	list-docker-images-project list-docker-volumes-project clean-docker-volumes-project \
	clean-docker-volumes-all clean-docker-build-cache clean-docker-build-cache-all \
	docker local prune

# Print a warning if there are unstaged/uncommitted changes.
clean-warning:
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  if git status --porcelain | grep -q .; then \
	    echo "[WARN] You have unstaged/uncommitted changes. 'make clean' will remove local envs, Docker resources, and caches, but won't delete your files."; \
	    git status --short; \
	  else \
	    echo "Working tree clean."; \
	  fi; \
	else \
	  echo "Not a git repository; proceeding."; \
	fi

# Local-only cleanup: virtualenv, build artifacts, caches, logs, sqlite
clean-local: clean-venv clean-build clean-pyc clean-caches clean-logs clean-sqlite

# Comprehensive local + Docker cleanup
clean: clean-warning clean-local clean-docker
	@echo "Clean complete."

# Build and packaging artifacts
clean-build:
	@echo "Removing build artifacts..."
	rm -rf build/ dist/ *.egg-info */*.egg-info **/*.egg-info
	rm -rf .coverage htmlcov coverage.xml .pytest_cache .mypy_cache .ruff_cache .cache

# Bytecode and __pycache__
clean-pyc:
	@echo "Removing Python bytecode and __pycache__..."
	find . -name "*.pyc" -delete || true
	find . -name "*.pyo" -delete || true
	find . -name "*~" -delete || true
	find . -name "__pycache__" -type d -exec rm -rf {} + || true

# Caches not covered elsewhere
clean-caches:
	@echo "Removing tool caches..."
	rm -rf .pytest_cache .mypy_cache .ruff_cache .cache || true

# Logs
clean-logs:
	@echo "Removing logs..."
	rm -rf logs/*.jsonl* || true

# SQLite test DBs and other local databases stored as files
clean-sqlite:
	@echo "Removing local SQLite databases..."
	rm -f adventorator_test.sqlite3 || true

# Virtual environment
clean-venv:
	@echo "Removing virtual environment..."
	rm -rf .venv

# Docker/Compose teardown for this project
clean-docker: clean-compose clean-docker-related

# Compose down with full cleanup: containers, orphans, volumes, images
clean-compose:
	@echo "Docker Compose: tear down containers/images/volumes/orphans..."
	@if [ -f docker-compose.yml ] || [ -f compose.yml ]; then \
	  docker compose down --remove-orphans --volumes --rmi all || true; \
	else \
	  echo "No compose file present, skipping docker compose down."; \
	fi

# Remove any stray containers, volumes, and networks associated with this project name
clean-docker-related:
	@echo "Removing stray Docker resources for this project..."
	@PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-$$(basename $$PWD)}; \
	PNLOW=$$(echo $$PROJECT_NAME | tr '[:upper:]' '[:lower:]'); \
	# Containers (names usually include project name)
	cons=$$(docker ps -a --format '{{.Names}}' | grep -i "$$PNLOW" || true); \
	# Also include ad-hoc DB container started via 'make db-up'
	if docker ps -a --format '{{.Names}}' | grep -q '^advdb$$'; then cons="$$cons advdb"; fi; \
	if [ -n "$$cons" ]; then echo "Removing containers: $$cons"; echo "$$cons" | xargs docker rm -f || true; else echo "No matching containers."; fi; \
	# Volumes (named volumes are typically <project>_<volume>)
	vols=$$(docker volume ls -q | grep -i "$$PNLOW" || true); \
	if [ -n "$$vols" ]; then echo "Removing volumes: $$vols"; echo "$$vols" | xargs docker volume rm -f || true; else echo "No matching volumes."; fi; \
	# Networks (compose default is <project>_default)
	nets=$$(docker network ls --format '{{.Name}}' | grep -i "$$PNLOW" || true); \
	if [ -n "$$nets" ]; then echo "Removing networks: $$nets"; echo "$$nets" | xargs docker network rm || true; else echo "No matching networks."; fi

# Optional: global prune of dangling images/volumes/networks (DANGEROUS if other projects rely on them)
clean-docker-prune:
	@echo "Pruning dangling Docker resources (images, containers, networks, build cache, and volumes)..."
	docker system prune -f --volumes || true

# Convenience aliases so you can run: `make clean docker` or just `make local`
docker: clean-docker
local: clean-local
prune: clean-docker-prune

# EXTREMELY DESTRUCTIVE: Remove ALL Docker images on this machine.
# Usage: CONFIRM=YES make clean-docker-all-images
# This will:
#  1) Stop and remove all containers (any project)
#  2) Remove all images (any project)
clean-docker-all-images:
	@if [ "$(CONFIRM)" != "YES" ]; then \
	  echo "Refusing to proceed. To confirm, run: CONFIRM=YES make clean-docker-all-images"; \
	  exit 1; \
	fi
	@echo "Stopping and removing ALL containers..."
	@ids=$$(docker ps -aq || true); if [ -n "$$ids" ]; then docker rm -f $$ids || true; else echo "No containers found."; fi
	@echo "Removing ALL images..."
	@imgs=$$(docker images -q || true); if [ -n "$$imgs" ]; then docker rmi -f $$imgs || true; else echo "No images found."; fi

# Safer middle-ground: remove images that are not used by any container (across machine)
clean-docker-unused-images:
	@echo "Removing all UNUSED Docker images (keeps images used by at least one container)..."
	docker image prune -a -f || true

# Scoped cleanup: remove only images that look like they belong to this project
# Heuristic: repository name starts with <project>- or <project>_
clean-docker-images-project:
	@PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-$$(basename $$PWD)}; \
	PNLOW=$$(echo $$PROJECT_NAME | tr '[:upper:]' '[:lower:]'); \
	imgs=$$(docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | awk -v p="$$PNLOW" 'tolower($$1) ~ "^" p "[-_]" {print $$2}' | sort -u); \
	if [ -n "$$imgs" ]; then echo "Removing project images: $$imgs"; echo "$$imgs" | xargs docker rmi -f || true; else echo "No project images found."; fi

# Helper: list candidate project images that would be removed by clean-docker-images-project
list-docker-images-project:
	@PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-$$(basename $$PWD)}; \
	PNLOW=$$(echo $$PROJECT_NAME | tr '[:upper:]' '[:lower:]'); \
	docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | awk -v p="$$PNLOW" 'tolower($$1) ~ "^" p "[-_]" {print $$0}' | sort || true

# Volumes: list project-labeled/likely volumes and remove them
list-docker-volumes-project:
	@PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-$$(basename $$PWD)}; \
	PNLOW=$$(echo $$PROJECT_NAME | tr '[:upper:]' '[:lower:]'); \
	docker volume ls -q | grep -i "^$$PNLOW[_-]" || true

clean-docker-volumes-project:
	@PROJECT_NAME=$${COMPOSE_PROJECT_NAME:-$$(basename $$PWD)}; \
	PNLOW=$$(echo $$PROJECT_NAME | tr '[:upper:]' '[:lower:]'); \
	vols=$$(docker volume ls -q | grep -i "^$$PNLOW[_-]" || true); \
	if [ -n "$$vols" ]; then echo "Removing project volumes: $$vols"; echo "$$vols" | xargs docker volume rm -f || true; else echo "No project volumes found."; fi

# Danger: remove ALL volumes on this machine (requires confirmation)
clean-docker-volumes-all:
	@if [ "$(CONFIRM)" != "YES" ]; then \
	  echo "Refusing to proceed. To confirm, run: CONFIRM=YES make clean-docker-volumes-all"; \
	  exit 1; \
	fi
	@echo "Removing ALL volumes..."
	@vols=$$(docker volume ls -q || true); if [ -n "$$vols" ]; then echo "$$vols" | xargs docker volume rm -f || true; else echo "No volumes found."; fi

# Build cache: prune safely (dangling cache only)
clean-docker-build-cache:
	@echo "Pruning Docker build cache (safe: dangling only)..."
	docker builder prune -f || true

# Build cache: nuke all cache (requires confirmation)
clean-docker-build-cache-all:
	@if [ "$(CONFIRM)" != "YES" ]; then \
	  echo "Refusing to proceed. To confirm, run: CONFIRM=YES make clean-docker-build-cache-all"; \
	  exit 1; \
	fi
	@echo "Pruning ALL Docker build cache (includes in-use cache for all builders)..."
	docker builder prune -a -f || true

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

# -------------- Campaign Package Workflow --------------
.PHONY: package-scaffold package-ids package-hash package-preflight package-import package-watch

# Scaffold a new package directory
# Usage: make package-scaffold DEST=campaigns/sample-campaign NAME="Greenhollow Demo"
package-scaffold:
	@if [ -z "$(DEST)" ]; then \
	  echo "DEST is required (e.g., make package-scaffold DEST=campaigns/sample-campaign NAME=\"Greenhollow Demo\")"; \
	  exit 1; \
	fi
	. .venv/bin/activate && python scripts/scaffold_package.py --dest "$(DEST)" $(if $(NAME),--name "$(NAME)")

# Assign ULID stable_id to entities missing/invalid IDs
# Usage: make package-ids PACKAGE_ROOT=campaigns/sample-campaign
package-ids:
	@if [ -z "$(PACKAGE_ROOT)" ]; then \
	  echo "PACKAGE_ROOT is required (e.g., make package-ids PACKAGE_ROOT=campaigns/sample-campaign)"; \
	  exit 1; \
	fi
	. .venv/bin/activate && python scripts/assign_entity_ids.py --package-root "$(PACKAGE_ROOT)"

# Recompute content_index hashes in manifest
# Usage: make package-hash PACKAGE_ROOT=campaigns/sample-campaign
package-hash:
	@if [ -z "$(PACKAGE_ROOT)" ]; then \
	  echo "PACKAGE_ROOT is required (e.g., make package-hash PACKAGE_ROOT=campaigns/sample-campaign)"; \
	  exit 1; \
	fi
	. .venv/bin/activate && python scripts/update_content_index.py --package-root "$(PACKAGE_ROOT)"

# DB preflight (checks tables; AUTO=1 to auto-migrate)
# Usage: make package-preflight [AUTO=1]
package-preflight:
	. .venv/bin/activate && python scripts/preflight_import.py $(if $(AUTO),--auto-migrate)

# End-to-end import (updates hashes unless NO_HASH_UPDATE=1, runs preflight unless SKIP_PREFLIGHT=1)
# Usage: make package-import PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1 [NO_EMBEDDINGS=1 SKIP_PREFLIGHT=1 NO_HASH_UPDATE=1 NO_IMPORTER=1]
package-import:
	@if [ -z "$(PACKAGE_ROOT)" ] || [ -z "$(CAMPAIGN_ID)" ]; then \
	  echo "PACKAGE_ROOT and CAMPAIGN_ID are required (e.g., make package-import PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1)"; \
	  exit 1; \
	fi
	. .venv/bin/activate && python scripts/import_package.py \
	  --package-root "$(PACKAGE_ROOT)" \
	  --campaign-id "$(CAMPAIGN_ID)" \
	  $(if $(NO_EMBEDDINGS),--no-embeddings) \
	  $(if $(SKIP_PREFLIGHT),--skip-preflight) \
	  $(if $(NO_HASH_UPDATE),--no-hash-update) \
	  $(if $(NO_IMPORTER),--no-importer)

# Watch a package for changes; IMPORT_ON_CHANGE=1 to auto-import; set INTERVAL=seconds (default 1.0)
# Usage: make package-watch PACKAGE_ROOT=campaigns/sample-campaign [CAMPAIGN_ID=1 IMPORT_ON_CHANGE=1 INTERVAL=1.0]
package-watch:
	@if [ -z "$(PACKAGE_ROOT)" ]; then \
	  echo "PACKAGE_ROOT is required (e.g., make package-watch PACKAGE_ROOT=campaigns/sample-campaign CAMPAIGN_ID=1 IMPORT_ON_CHANGE=1)"; \
	  exit 1; \
	fi
	. .venv/bin/activate && python scripts/watch_package.py \
	  --package-root "$(PACKAGE_ROOT)" \
	  $(if $(CAMPAIGN_ID),--campaign-id "$(CAMPAIGN_ID)") \
	  $(if $(IMPORT_ON_CHANGE),--import-on-change) \
	  $(if $(INTERVAL),--interval "$(INTERVAL)")

