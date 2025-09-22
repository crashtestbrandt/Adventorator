# Copilot Environment Configuration

This document describes the environment setup and requirements for the Adventorator project when working with GitHub Copilot coding agents.

## Required Environment Variables

### Core Discord Integration (Required - Store as Secrets)
- `DISCORD_APP_ID` - Discord application ID (numeric string)
- `DISCORD_PUBLIC_KEY` - Discord application public key for webhook verification
- `DISCORD_GUILD_ID` - Discord server ID where the bot operates
- `DISCORD_BOT_TOKEN` - Discord bot authentication token (**SECRET**)
- `DISCORD_DEV_PUBLIC_KEY` - Development Discord public key (**SECRET**)

### Database Configuration
- `POSTGRES_USER` - Database username (default: `adventorator`)
- `POSTGRES_PASSWORD` - Database password (default: `adventorator`)
- `POSTGRES_DB` - Database name (default: `adventorator`)
- `DATABASE_URL` - Full database connection string (format: `postgresql+asyncpg://user:pass@host:port/db`)
- `DB_PORT` - PostgreSQL port (default: `5432`)

### Application Configuration
- `APP_PORT` - Application server port (default: `18000`)
- `ENV` - Environment name (default: `dev`)

### LLM Integration (Optional)
- `LLM_API_URL` - LLM service endpoint (default: `http://host.docker.internal:11434`)
- `LLM_MODEL_NAME` - Model to use (default: `dolphin-mistral:7b`)
- `LLM_API_PROVIDER` - Provider type (default: `ollama`)
- `LLM_API_KEY` - API authentication key (default: `ollama`)

### Feature Flags
- `FEATURES_MCP` - Enable MCP integration (default: `true`)
- `FEATURES_LLM` - Enable LLM features (default: `true`)
- `FEATURES_LLM_VISIBLE` - Show LLM features in UI (default: `true`)

### Optional Development Overrides
- `DISCORD_WEBHOOK_URL_OVERRIDE` - Override webhook URL for development
- `PYTHONPATH` - Python module search path (auto-set to `./src` by Makefile)

## Required Outbound Domains and Ports

### Package Registries and Dependencies
- `pypi.org:443` - Python package index
- `files.pythonhosted.org:443` - Python package downloads
- `astral.sh:443` - UV package manager installation
- `registry.npmjs.org:443` - Node.js package registry
- `docker.io:443` - Docker Hub container registry
- `registry.hub.docker.com:443` - Docker Hub registry
- `index.docker.io:443` - Docker Hub index

### Service Dependencies
- `postgres:5432` - PostgreSQL database (container or external)
- `discord.com:443` - Discord API endpoints
- `discordapp.com:443` - Discord CDN and webhook endpoints

### Optional External Services
- `ollama.ai:443` - Ollama model downloads (if using LLM features)
- Custom LLM provider endpoints (configurable via `LLM_API_URL`)

## Quick-Start Commands

### Unit Tests (Standalone)
```bash
make test
# Or with coverage
make coverage
```

### Linting and Code Quality
```bash
make lint          # Check code style
make lint-fix      # Auto-fix issues
make type          # Type checking with mypy
make format        # Format code with ruff
```

### Quality Gates (Comprehensive)
```bash
make quality-gates  # Runs coverage, mutation-guard, security, quality-artifacts, ai-evals
```

### Building and Development
```bash
make dev           # Set up development environment
make run           # Start development server
make run-dev       # Kill conflicting processes and start server
```

### Database Operations (Requires PostgreSQL)
```bash
make db-up         # Start PostgreSQL container
make db-upgrade    # Run Alembic migrations
```

### Docker Compose (Full Environment)
```bash
make compose-up           # Start all services
make compose-dev          # Start with .env.docker file
make compose-dev-auto     # Auto-select free ports
make compose-clean        # Stop and remove all data
```

## Tasks Requiring Ephemeral Services

### Database-Dependent Tests
- Integration tests that verify database operations
- Alembic migration tests
- Repository layer tests
- End-to-end API tests

**Service**: PostgreSQL 16 container
**Startup**: `make db-up` or `docker run postgres:16` with health checks
**Port**: 5432 (auto-select alternative if occupied)

### Discord Integration Tests
- Webhook verification tests
- Command registration tests
- Interaction handling tests

**Service**: Discord API (external)
**Requirements**: Valid Discord bot tokens and webhook URLs

## Standalone Tasks (No Services Required)

- Unit tests for business logic
- Linting and formatting
- Type checking
- Static security analysis
- Prompt and contract validation
- Most AI evaluation tests

## Environment Setup Notes

### Copilot Agent Considerations
- **Ephemeral services**: Always use on-demand startup, not persistent background servers
- **Port management**: Auto-detect free ports to avoid conflicts
- **Health checks**: Wait for services to be ready before running tests
- **Cleanup**: Stop services after test completion to free resources
- **Caching**: Use dependency caching to speed up repeated setups

### Python Environment
- **Version**: Python 3.12+ required
- **Package manager**: Prefers `uv` for speed, falls back to `pip`
- **Virtual environment**: Always use `.venv` directory
- **PYTHONPATH**: Set to `./src` for imports

### Docker Requirements
- **PostgreSQL**: Uses official `postgres:16` image
- **Health checks**: Built-in `pg_isready` command
- **Data persistence**: Uses named volumes in compose, ephemeral in tests
- **Resource limits**: Minimal settings for development (no production tuning)

## Troubleshooting Common Issues

### Port Conflicts
```bash
# Check what's using a port
sudo lsof -i :5432
sudo lsof -i :18000

# Kill processes using ports
make kill-port      # Kills process on :18000
make kill-db-port   # Kills process on :5432
```

### Memory Errors
- Ensure Docker has at least 4GB RAM allocated
- Consider using `make compose-dev-auto` for automatic port selection
- Stop unused containers: `docker container prune`

### Docker Not Running
```bash
# Check Docker daemon status
sudo systemctl status docker

# Start Docker (Linux)
sudo systemctl start docker

# Verify Docker installation
docker --version
docker run hello-world
```

### Database Connection Issues
```bash
# Test PostgreSQL connection
docker exec test-postgres pg_isready -U adventorator -d adventorator

# Check container logs
docker logs test-postgres

# Reset database
make compose-clean && make compose-up
```

### Python Import Errors
```bash
# Verify PYTHONPATH
echo $PYTHONPATH

# Reinstall package in development mode
pip install -e .

# Check package installation
python -c "import Adventorator; print('OK')"
```

### UV Package Manager Issues
```bash
# Install uv manually if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Fallback to pip if uv fails
pip install -r requirements.txt
pip install -e .
```

## Security Considerations

- **Never commit secrets**: Use `.env.docker` (gitignored) for local development
- **Firewall allowlist**: Add required domains to repository settings for Copilot agents
- **Token rotation**: Regularly rotate Discord bot tokens and database passwords
- **Minimal permissions**: Use least-privilege access for database and Discord bot roles

## Configuration Outside Workflow

### Required Repository Settings (Admin Only)
1. **Copilot allowlist**: Add domains listed above to repository's Copilot coding agent settings
2. **Secrets**: Store sensitive environment variables as repository secrets
3. **Branch protection**: Ensure quality gates run on pull requests

### Local Development Setup
1. Copy `.env.docker.example` to `.env.docker`
2. Replace placeholder values with actual Discord tokens
3. Run `make compose-dev` to start full environment
4. Access application at `http://localhost:18000`

This configuration ensures Copilot agents can efficiently set up the development environment with all necessary dependencies and services.