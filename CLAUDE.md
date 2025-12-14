# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Development instance runs at `https://awhite-psagent.ngrok.app` (GitHub webhook target).

## Commands

### Development
```bash
# Install dependencies (including dev)
uv sync --all-extras

# Run web server (requires PostgreSQL running)
uv run uvicorn procrasturbate.main:app --reload

# Run background worker (separate terminal)
uv run procrastinate worker --app=procrasturbate.tasks.worker.app

# Database migrations
uv run alembic upgrade head    # Apply all migrations
uv run alembic revision --autogenerate -m "description"  # Create new migration
```

### Testing & Quality
```bash
uv run pytest                  # Run all tests
uv run pytest tests/test_diff_parser.py  # Run single test file
uv run pytest -k "test_name"   # Run tests matching pattern
uv run ruff check .            # Lint
uv run ruff format .           # Format
uv run mypy src                # Type check
```

### Docker (Production)
```bash
cd docker && docker-compose up -d
docker-compose exec app alembic upgrade head
```

## Architecture

### Two Database Connections
The app uses PostgreSQL with two separate connection strings for different async drivers:
- `DATABASE_URL` (asyncpg): SQLAlchemy async ORM via `database.py`
- `PROCRASTINATE_DATABASE_URL` (psycopg): Procrastinate task queue via `tasks/worker.py`

### Request Flow
1. **Webhook** (`api/webhooks.py`): GitHub sends PR/comment events, validated via HMAC signature
2. **Task Queue** (`tasks/review_tasks.py`): Events deferred to Procrastinate for async processing
3. **Review Engine** (`services/review_engine.py`): Orchestrates the review - loads config, checks budget, fetches diff, calls Claude, posts results
4. **Claude Client** (`services/claude_client.py`): Builds prompts with repo-specific rules, parses JSON response

### Key Services
- `services/github_client.py`: Async httpx client with JWT auth for GitHub API
- `services/diff_parser.py`: Parses unified diff format, maps line numbers to diff positions
- `services/config_loader.py`: Loads `.aireviewer.yaml` from repos for per-repo settings
- `services/cost_tracker.py`: Tracks token usage and enforces monthly budgets
- `services/comment_commands.py`: Parses `@reviewer` commands from PR comments

### Models
`Installation` → `Repository` → `Review` → `ReviewComment`

Plus `UsageRecord` for monthly cost tracking per installation.

### Configuration
Per-repo config via `.aireviewer.yaml` in target repos controls:
- Which rules to apply (security, performance, style, bugs, documentation, custom)
- Path include/exclude patterns
- Auto-review triggers (opened, synchronize, reopened)
- Context files to include in prompts
- Language/framework hints

## Testing Notes
- Tests use SQLite in-memory (`conftest.py`) instead of PostgreSQL
- Requires `aiosqlite` for async SQLite support in tests
- `pytest-asyncio` with `asyncio_mode = "auto"` for async test functions
