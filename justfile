# justfile - https://github.com/casey/just
set dotenv-load := true

default:
    @just --list

# Install the locked runtime and development dependencies.
sync:
    uv sync --locked --extra test --extra lint --extra docs

lint:
    uv run --no-sync ruff check backend/app backend/tests scripts

fix:
    uv run --no-sync ruff check --fix backend/app backend/tests scripts

fmt:
    uv run --no-sync ruff format backend/app backend/tests scripts

fmt-check:
    uv run --no-sync ruff format --check backend/app backend/tests scripts

typecheck:
    uv run --no-sync pyright

test:
    uv run --no-sync pytest backend/tests/unit -q

test-cov:
    uv run --no-sync pytest backend/tests/unit --cov=app --cov-report=term-missing -q

test-one *args:
    uv run --no-sync pytest {{ args }}

# Rebuild the Markdown-derived HTML and PDF handbook artifacts.
handbook:
    uv run --no-sync python scripts/build_handbook.py

dev port="8000":
    uv run --no-sync uvicorn app.main:app --reload --reload-dir backend --host 127.0.0.1 --port {{ port }} --app-dir backend

serve port="8000":
    uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port {{ port }} --app-dir backend

up:
    docker compose up -d

logs:
    docker compose logs -f

down:
    docker compose down

migrate:
    uv run --no-sync alembic upgrade head

migrate-current:
    uv run --no-sync alembic current

# Preview release changes without committing or pushing them.
release-dry-run bump="patch":
    uv run --no-sync python scripts/release.py --bump {{ bump }} --dry-run
