.PHONY: help sync fmt lint typecheck test test-unit test-integration test-contract run-fetch run-gateway create clean

help:
	@echo "sync            Install/refresh deps with uv"
	@echo "fmt             Format with ruff"
	@echo "lint            Lint with ruff"
	@echo "typecheck       Type-check with mypy"
	@echo "test            Run all tests"
	@echo "test-unit       Run unit tests only"
	@echo "test-contract   Run contract tests only"
	@echo "run-fetch       Run the fetch pilot server"
	@echo "run-gateway     Run the aggregation gateway"
	@echo "create NAME=x   Scaffold a new server"

sync:
	uv sync --all-extras

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/mcp_common gateway

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test-contract:
	uv run pytest -m contract

run-fetch:
	uv run python -m servers.fetch

run-gateway:
	uv run mcp-gateway

create:
	@if [ -z "$(NAME)" ]; then echo "Usage: make create NAME=<server-name>"; exit 1; fi
	uv run mcp-create --name $(NAME)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
