set dotenv-load := true

default:
    @just --list

sync:
    uv sync --locked --extra test --extra lint --extra docs

lint:
    uv run --no-sync ruff check paperplane tests streamlit_app.py scripts

fix:
    uv run --no-sync ruff check --fix paperplane tests streamlit_app.py scripts

fmt:
    uv run --no-sync ruff format paperplane tests streamlit_app.py scripts

fmt-check:
    uv run --no-sync ruff format --check paperplane tests streamlit_app.py scripts

typecheck:
    uv run --no-sync pyright

test:
    uv run --no-sync pytest tests -q

test-cov:
    uv run --no-sync pytest tests --cov=paperplane --cov-report=term-missing -q

test-one *args:
    uv run --no-sync pytest {{ args }}

docs:
    uv run --no-sync python scripts/build_handbook.py
    uv run --no-sync python scripts/build_app_guide.py

dev:
    uv run --locked streamlit run streamlit_app.py

release-dry-run bump="patch":
    uv run --no-sync python scripts/release.py --bump {{ bump }} --dry-run
